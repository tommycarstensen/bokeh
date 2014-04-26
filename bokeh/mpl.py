""" Supporting objects and functions to convert Matplotlib objects into Bokeh

"""

import warnings
import numpy as np
import matplotlib as mpl
from itertools import (cycle, islice)

from scipy import interpolate, signal

from .objects import (Plot, DataRange1d, LinearAxis, ColumnDataSource, Glyph,
                      Grid, PanTool, WheelZoomTool)
from .glyphs import (Line, Circle, Square, Cross, Triangle, InvertedTriangle,
                     Xmarker, Diamond, Asterisk, MultiLine, Patches)


# This is used to accumulate plots generated via the plotting methods in this
# module.  It is used by build_gallery.py.  To activate this feature, simply
# set _PLOTLIST to an empty list; to turn it off, set it back to None.
_PLOTLIST = None


def axes2plot(ax, xkcd):
    """ In the matplotlib object model, Axes actually are containers for all
    renderers and basically everything else on a plot.

    This takes an MPL Axes object and returns a list of Bokeh objects
    corresponding to it.
    """

    # Get axis background color
    background_fill = ax.get_axis_bgcolor()
    if background_fill == 'w':
        background_fill = 'white'
    title = ax.get_title()
    plot = Plot(title=title, background_fill=background_fill)
    if xkcd:
        plot.title_text_font = "Comic Sans MS, Textile, cursive"
        plot.title_text_font_style = "bold"
        plot.title_text_color = "black"
    if _PLOTLIST is not None:
        _PLOTLIST.append(plot)
    plot.x_range = DataRange1d()
    plot.y_range = DataRange1d()
    datasource = ColumnDataSource()
    plot.data_sources = [datasource]

    # Break up the lines and markers by filtering on linestyle and marker style
    lines = [line for line in ax.lines if line.get_linestyle() not in ("", " ", "None", "none", None)]
    markers = [m for m in ax.lines if m.get_marker() not in ("", " ", "None", "none", None)]
    cols = [col for col in ax.collections if col.get_paths() not in ("", " ", "None", "none", None)]
    renderers = [_make_line(datasource, plot.x_range, plot.y_range, line, xkcd) for line in lines]
    renderers.extend(_make_marker(datasource, plot.x_range, plot.y_range, marker) for marker in markers)
    renderers.extend(_make_lines_collection(datasource, plot.x_range, plot.y_range, col, xkcd) \
                        for col in cols if isinstance(col, mpl.collections.LineCollection))
    renderers.extend(_make_polys_collection(datasource, plot.x_range, plot.y_range, col) \
                        for col in cols if isinstance(col, mpl.collections.PolyCollection))
    plot.renderers.extend(renderers)

    # xaxis
    xaxis = _make_axis(plot, ax.xaxis, 0, xkcd)

    # yaxis
    yaxis = _make_axis(plot, ax.yaxis, 1, xkcd)

    # xgrid
    _make_grid(plot, ax.get_xgridlines()[0], xaxis, 0)

    # ygrid
    _make_grid(plot, ax.get_xgridlines()[0], yaxis, 1)

    # Add tools
    pantool = PanTool(dimensions=["width", "height"])
    wheelzoom = WheelZoomTool(dimensions=["width", "height"])
    plot.tools = [pantool, wheelzoom]
    return plot


def _convert_color(mplcolor):
    charmap = dict(b="blue", g="green", r="red", c="cyan", m="magenta",
                   y="yellow", k="black", w="white")
    if mplcolor in charmap:
        return charmap[mplcolor]

    try:
        colorfloat = float(mplcolor)
        if 0 <= colorfloat <= 1.0:
            # This is a grayscale value
            return tuple([int(255 * colorfloat)] * 3)
    except:
        pass

    if isinstance(mplcolor, tuple):
        # These will be floats in the range 0..1
        return int(255 * mplcolor[0]), int(255 * mplcolor[1]), int(255 * mplcolor[2])

    return mplcolor


def _convert_dashes(dash):
    """ Converts a Matplotlib dash specification

    bokeh.properties.DashPattern supports the matplotlib named dash styles,
    but not the little shorthand characters.  This function takes care of
    mapping those.
    """
    mpl_dash_map = {
        "-": "solid",
        "--": "dashed",
        ":": "dotted",
        "-.": "dashdot",
    }
    # If the value doesn't exist in the map, then just return the value back.
    return mpl_dash_map.get(dash, dash)


def _get_props_cycled(col, prop, fx=lambda x: x):
    """ We need to cycle the `get.property` list (where property can be colors,
    line_width, etc) as matplotlib does. We use itertools tools for do this
    cycling ans slice manipulation.

    Parameters:

    col: matplotlib collection object
    prop: property we want to get from matplotlib collection
    fx: funtion (optional) to transform the elements from list obtained
        after the property call. Deafults to identity function.
    """
    n = len(col.get_paths())
    t_prop = [fx(x) for x in prop]
    sliced = islice(cycle(t_prop), None, n)
    return list(sliced)


def _delete_last_col(x):
    x = np.delete(x, (-1), axis=1)
    return x


def line_props(line, line2d):
    cap_style_map = {
        "butt": "butt",
        "round": "round",
        "projecting": "square",
    }
    line.line_color = line2d.get_color()
    line.line_width = line2d.get_linewidth()
    line.line_alpha = line2d.get_alpha()
    # TODO: how to handle dash_joinstyle?
    line.line_join = line2d.get_solid_joinstyle()
    line.line_cap = cap_style_map[line2d.get_solid_capstyle()]
    line.line_dash = _convert_dashes(line2d.get_linestyle())
    # setattr(newline, "line_dash_offset", ...)


def marker_props(marker, line2d):
    marker.line_color = line2d.get_markeredgecolor()
    marker.fill_color = line2d.get_markerfacecolor()
    marker.line_width = line2d.get_markeredgewidth()
    marker.size = line2d.get_markersize()
    # Is this the right way to handle alpha? MPL doesn't seem to distinguish
    marker.fill_alpha = marker.line_alpha = line2d.get_alpha()


def multiline_props(source, multiline, col):
    colors = _get_props_cycled(col, col.get_colors(), fx=lambda x: mpl.colors.rgb2hex(x))
    widths = _get_props_cycled(col, col.get_linewidth())
    multiline.line_color = source.add(colors)
    multiline.line_width = source.add(widths)
    multiline.line_alpha = col.get_alpha()
    offset = col.get_linestyle()[0][0]
    if not col.get_linestyle()[0][1]:
        on_off = []
    else:
        on_off = map(int,col.get_linestyle()[0][1])
    multiline.line_dash_offset = _convert_dashes(offset)
    multiline.line_dash = list(_convert_dashes(tuple(on_off)))


def patches_props(source, patches, col):
    face_colors = _get_props_cycled(col, col.get_facecolors(), fx=lambda x: mpl.colors.rgb2hex(x))
    patches.fill_color = source.add(face_colors)
    edge_colors = _get_props_cycled(col, col.get_edgecolors(), fx=lambda x: mpl.colors.rgb2hex(x))
    patches.line_color = source.add(edge_colors)
    widths = _get_props_cycled(col, col.get_linewidth())
    patches.line_width = source.add(widths)
    patches.line_alpha = col.get_alpha()
    offset = col.get_linestyle()[0][0]
    if not col.get_linestyle()[0][1]:
        on_off = []
    else:
        on_off = map(int,col.get_linestyle()[0][1])
    patches.line_dash_offset = _convert_dashes(offset)
    patches.line_dash = list(_convert_dashes(tuple(on_off)))


def text_props(mplText, obj, prefix=""):
    """ Sets various TextProps on a bokeh object based on values from a
    matplotlib Text object.  An optional prefix is added to the TextProps
    field names, to mirror the common use of the TextProps property.
    """
    alignment_map = {"center": "middle", "top": "top", "bottom": "bottom"}  # TODO: support "baseline"
    fontstyle_map = {"oblique": "italic", "normal": "normal", "italic": "italic"}

    setattr(obj, prefix+"text_font_style", fontstyle_map[mplText.get_fontstyle()])
    # we don't really have the full range of font weights, but at least handle bold
    if mplText.get_weight() in ("bold", "heavy"):
        setattr(obj, prefix+"text_font_style", "bold")
    setattr(obj, prefix+"text_font_size", "%dpx" % mplText.get_fontsize())
    setattr(obj, prefix+"text_alpha", mplText.get_alpha())
    setattr(obj, prefix+"text_color", _convert_color(mplText.get_color()))
    setattr(obj, prefix+"text_baseline", alignment_map[mplText.get_verticalalignment()])

    # Using get_fontname() works, but it's oftentimes not available in the browser,
    # so it's better to just use the font family here.
    #setattr(obj, prefix+"text_font", mplText.get_fontname())
    setattr(obj, prefix+"text_font", mplText.get_fontfamily()[0])


def _make_axis(plot, ax, dimension, xkcd):
    """ Given an mpl.Axis instance, returns a bokeh LinearAxis """
    # TODO:
    #  * handle `axis_date`, which treats axis as dates
    #  * handle log scaling
    #  * map `labelpad` to `major_label_standoff`
    #  * deal with minor ticks once BokehJS supports them
    #  * handle custom tick locations once that is added to bokehJS

    laxis = LinearAxis(plot=plot, dimension=dimension, location="min",
                       axis_label=ax.get_label_text())

    # First get the label properties by getting an mpl.Text object
    label = ax.get_label()
    text_props(label, laxis, prefix="axis_label_")

    # To get the tick label format, we look at the first of the tick labels
    # and assume the rest are formatted similarly.
    ticktext = ax.get_ticklabels()[0]
    text_props(ticktext, laxis, prefix="major_label_")

    #newaxis.bounds = axis.get_data_interval()  # I think this is the right func...

    if xkcd:
        laxis.axis_line_width = 3
        laxis.axis_label_text_font = "Comic Sans MS, Textile, cursive"
        laxis.axis_label_text_font_style = "bold"
        laxis.axis_label_text_color = "black"
        laxis.major_label_text_font = "Comic Sans MS, Textile, cursive"
        laxis.major_label_text_font_style = "bold"
        laxis.major_label_text_color = "black"

    return laxis


def _make_grid(plot, grid, ax, dimension):

    Grid(plot=plot, dimension=dimension, axis=ax,
         grid_line_color=grid.get_color(), grid_line_width=grid.get_linewidth())


def _make_line(source, xdr, ydr, line2d, xkcd):
    ""
    xydata = line2d.get_xydata()
    x = xydata[:, 0]
    y = xydata[:, 1]
    if xkcd:
        x, y = xkcd_line(x, y)

    line = Line()
    line.x = source.add(x)
    line.y = source.add(y)
    xdr.sources.append(source.columns(line.x))
    ydr.sources.append(source.columns(line.y))

    line_props(line, line2d)
    if xkcd:
        line.line_width = 3

    line_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=line)
    return line_glyph


def _make_marker(source, xdr, ydr, line2d):
    """ Given a matplotlib line2d instance that has non-null marker type,
    return an appropriate Bokeh Marker glyph.
    """
    marker_map = {
        "o": Circle,
        "s": Square,
        "+": Cross,
        "^": Triangle,
        "v": InvertedTriangle,
        "x": Xmarker,
        "D": Diamond,
        "*": Asterisk,
    }
    if line2d.get_marker() not in marker_map:
        warnings.warn("Unable to handle marker: %s" % line2d.get_marker())
    marker = marker_map[line2d.get_marker()]()

    xydata = line2d.get_xydata()
    x = xydata[:, 0]
    y = xydata[:, 1]
    marker.x = source.add(x)
    marker.y = source.add(y)
    xdr.sources.append(source.columns(marker.x))
    ydr.sources.append(source.columns(marker.y))

    marker_props(marker, line2d)

    marker_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=marker)
    return marker_glyph


def _make_lines_collection(source, xdr, ydr, col, xkcd):
    ""
    xydata = col.get_segments()
    t_xydata = [np.transpose(seg) for seg in xydata]
    xs = [t_xydata[x][0] for x in range(len(t_xydata))]
    ys = [t_xydata[x][1] for x in range(len(t_xydata))]
    if xkcd:
        xkcd_xs = [xkcd_line(xs[i], ys[i])[0] for i in range(len(xs))]
        xkcd_ys = [xkcd_line(xs[i], ys[i])[1] for i in range(len(ys))]
        xs = xkcd_xs
        ys = xkcd_ys

    multiline = MultiLine()
    multiline.xs = source.add(xs)
    multiline.ys = source.add(ys)
    xdr.sources.append(source.columns(multiline.xs))
    ydr.sources.append(source.columns(multiline.ys))

    multiline_props(source, multiline, col)

    multiline_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=multiline)
    return multiline_glyph


def _make_polys_collection(source, xdr, ydr, col):
    ""
    paths = col.get_paths()
    polygons = [paths[i].to_polygons() for i in range(len(paths))]
    polygons = [np.transpose(_delete_last_col(polygon)) for polygon in polygons]
    xs = [polygons[i][0] for i in range(len(polygons))]
    ys = [polygons[i][1] for i in range(len(polygons))]

    patches = Patches()
    patches.xs = source.add(xs)
    patches.ys = source.add(ys)
    xdr.sources.append(source.columns(patches.xs))
    ydr.sources.append(source.columns(patches.ys))

    patches_props(source, patches, col)

    patches_glyph = Glyph(data_source=source, xdata_range=xdr, ydata_range=ydr, glyph=patches)
    return patches_glyph


def xkcd_line(x, y, xlim=None, ylim=None, mag=1.0, f1=30, f2=0.001, f3=5):
    """
    Mimic a hand-drawn line from (x, y) data
    Source: http://jakevdp.github.io/blog/2012/10/07/xkcd-style-plots-in-matplotlib/

    Parameters
    ----------
    x, y : array_like
        arrays to be modified
    xlim, ylim : data range
        the assumed plot range for the modification.  If not specified,
        they will be guessed from the  data
    mag : float
        magnitude of distortions
    f1, f2, f3 : int, float, int
        filtering parameters.  f1 gives the size of the window, f2 gives
        the high-frequency cutoff, f3 gives the size of the filter

    Returns
    -------
    x, y : ndarrays
        The modified lines
    """
    x = np.asarray(x)
    y = np.asarray(y)

    # get limits for rescaling
    if xlim is None:
        xlim = (x.min(), x.max())
    if ylim is None:
        ylim = (y.min(), y.max())

    if xlim[1] == xlim[0]:
        xlim = ylim

    if ylim[1] == ylim[0]:
        ylim = xlim

    # scale the data
    x_scaled = (x - xlim[0]) * 1. / (xlim[1] - xlim[0])
    y_scaled = (y - ylim[0]) * 1. / (ylim[1] - ylim[0])

    # compute the total distance along the path
    dx = x_scaled[1:] - x_scaled[:-1]
    dy = y_scaled[1:] - y_scaled[:-1]
    dist_tot = np.sum(np.sqrt(dx * dx + dy * dy))

    # number of interpolated points is proportional to the distance
    Nu = int(200 * dist_tot)
    u = np.arange(-1, Nu + 1) * 1. / (Nu - 1)

    # interpolate curve at sampled points
    k = min(3, len(x) - 1)
    res = interpolate.splprep([x_scaled, y_scaled], s=0, k=k)
    x_int, y_int = interpolate.splev(u, res[0])

    # we'll perturb perpendicular to the drawn line
    dx = x_int[2:] - x_int[:-2]
    dy = y_int[2:] - y_int[:-2]
    dist = np.sqrt(dx * dx + dy * dy)

    # create a filtered perturbation
    coeffs = mag * np.random.normal(0, 0.01, len(x_int) - 2)
    b = signal.firwin(f1, f2 * dist_tot, window=('kaiser', f3))
    response = signal.lfilter(b, 1, coeffs)

    x_int[1:-1] += response * dy / dist
    y_int[1:-1] += response * dx / dist

    # un-scale data
    x_int = x_int[1:-1] * (xlim[1] - xlim[0]) + xlim[0]
    y_int = y_int[1:-1] * (ylim[1] - ylim[0]) + ylim[0]

    return x_int, y_int
