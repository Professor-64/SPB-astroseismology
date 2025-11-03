import os, numpy as np
from types import MethodType

from bokeh.io import output_notebook, show
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool, Span, Slider, CustomJS, Div
from bokeh.layouts import column

def attach_tripanel(info):
    def plot_tripanel(self,
                      width: int = 1000,
                      height_each: int = 260,
                      allow_ws_origin: str = "*",
                      color_centroid: str = "red",
                      color_raw: str = "navy",
                      color_trend: str = "orange",
                      marker_raw: str = None,     # bv. "circle" voor punten; None = lijn
                      marker_size: int = 3,
                      separate_intervals: bool = True,
                      separate_threshold: float = 1.5,   # zoals in je referentie
                      ):
        # --- helpers ---
        def nanstrip(t, y):
            m = np.isfinite(t) & np.isfinite(y)
            return t[m], y[m]

        def segment_xy(t, y, thresh=10.0):
            """Splits t,y in segmenten volgens dtime > thresh * dtime.min() (zoals referentie)."""
            t, y = nanstrip(np.asarray(t), np.asarray(y))
            if t.size < 2:
                return [t.tolist()], [y.tolist()]
            dt = np.diff(t)
            # alleen positieve/finiete dt’s
            good = np.isfinite(dt) & (dt > 0)
            if not np.any(good):
                return [t.tolist()], [y.tolist()]
            dt_pos = dt[good]
            base = np.min(dt_pos)
            # indices waar we knippen
            cut_idx = np.where(dt > thresh * base)[0] + 1
            # np.split verwacht indexen in de array (niet in diff), dus dit is juist
            t_segs = np.split(t, cut_idx)
            y_segs = np.split(y, cut_idx)
            return [seg.tolist() for seg in t_segs], [seg.tolist() for seg in y_segs]

        def median_dt_for_slider(t):
            t = np.asarray(t)
            if t.size < 2:
                return np.nan
            dt = np.diff(t)
            dt = dt[np.isfinite(dt) & (dt > 0)]
            return float(np.nanmedian(dt)) if dt.size else np.nan

        # VS Code webview fix
        if allow_ws_origin:
            os.environ["BOKEH_ALLOW_WS_ORIGIN"] = allow_ws_origin

        output_notebook()

        # ---------- DATA ----------
        # CENTROIDS
        t_cent = np.asarray(self.centroids.time)
        y_cent = np.asarray(self.centroids.sqrt_col2_row2)
        # RAW/REGRESSED (info.lc_regressed_clean)
        t_reg = np.asarray(self.lc_regressed_clean.time.value)
        y_reg = np.asarray(self.lc_regressed_clean.flux.value)
        # TREND (info.lc_trend)
        t_tr  = np.asarray(self.lc_trend.time.value)
        y_tr  = np.asarray(self.lc_trend.flux.value)

        # Segmentatie
        if separate_intervals:
            xs_cent, ys_cent = segment_xy(t_cent, y_cent, separate_threshold)
            xs_raw,  ys_raw  = segment_xy(t_reg,  y_reg,  separate_threshold)
            xs_tr,   ys_tr   = segment_xy(t_tr,   y_tr,   separate_threshold)
        else:
            xs_cent, ys_cent = [t_cent.tolist()], [y_cent.tolist()]
            xs_raw,  ys_raw  = [t_reg.tolist()],  [y_reg.tolist()]
            xs_tr,   ys_tr   = [t_tr.tolist()],   [y_tr.tolist()]

        # “Platte” bronnen voor slider/hover (dichtstbijzijnde punt zoeken)
        flat_cent_t = np.concatenate([np.asarray(x) for x in xs_cent]) if xs_cent else np.array([])
        flat_cent_y = np.concatenate([np.asarray(y) for y in ys_cent]) if ys_cent else np.array([])
        flat_raw_t  = np.concatenate([np.asarray(x) for x in xs_raw])  if xs_raw  else np.array([])
        flat_raw_y  = np.concatenate([np.asarray(y) for y in ys_raw])  if ys_raw  else np.array([])
        flat_tr_t   = np.concatenate([np.asarray(x) for x in xs_tr])   if xs_tr   else np.array([])
        flat_tr_y   = np.concatenate([np.asarray(y) for y in ys_tr])   if ys_tr   else np.array([])

        # Slider step: voorkeur mediane dt op centroids; val terug op raw/trend
        step = median_dt_for_slider(flat_cent_t)
        if not np.isfinite(step):
            step = median_dt_for_slider(flat_raw_t)
        if not np.isfinite(step):
            step = median_dt_for_slider(flat_tr_t)
        if not np.isfinite(step) or step <= 0:
            step = 1.0

        # ColumnDataSources
        # voor multi_line
        src_cent_segments = ColumnDataSource(dict(xs=xs_cent, ys=ys_cent))
        src_raw_segments  = ColumnDataSource(dict(xs=xs_raw,  ys=ys_raw))
        src_tr_segments   = ColumnDataSource(dict(xs=xs_tr,   ys=ys_tr))
        # voor slider/hover (dichtstbijzijnde)
        src_cent_pts = ColumnDataSource(dict(time=flat_cent_t, y=flat_cent_y))
        src_raw_pts  = ColumnDataSource(dict(time=flat_raw_t,  y=flat_raw_y))
        src_tr_pts   = ColumnDataSource(dict(time=flat_tr_t,   y=flat_tr_y))

        # ---------- FIGURES ----------
        title_prefix = f"TIC {getattr(self,'tic','?')} • Sector {getattr(self,'sector','?')}"
        p_cent = figure(width=width, height=height_each,
                        title=f"{title_prefix} — Centroid",
                        tools="pan,wheel_zoom,box_zoom,reset,save")
        p_tr   = figure(width=width, height=height_each,
                        title=f"{title_prefix} — Trend",
                        tools="pan,wheel_zoom,box_zoom,reset,save",
                        x_range=p_cent.x_range)
        p_raw  = figure(width=width, height=height_each,
                        title=f"{title_prefix} — Regressed flux",
                        tools="pan,wheel_zoom,box_zoom,reset,save",
                        x_range=p_cent.x_range)

        # Aslabels
        p_cent.xaxis.axis_label = "Time (BTJD)"
        p_cent.yaxis.axis_label = "Pix"
        p_raw.xaxis.axis_label  = "Time (BTJD)"
        p_raw.yaxis.axis_label  = "Flux (RAW)"
        p_tr.xaxis.axis_label   = "Time (BTJD)"
        p_tr.yaxis.axis_label   = "Flux (Trend)"

        # Plotten zonder gaps
        p_cent.multi_line(xs="xs", ys="ys", source=src_cent_segments, line_color=color_centroid)

        if marker_raw:
            # enkel punten, geen verbinding over gaps
            p_raw.scatter("time", "y", source=src_raw_pts, marker=marker_raw,
                          size=marker_size, alpha=0.9, line_color=None, fill_color=color_raw)
        else:
            p_raw.multi_line(xs="xs", ys="ys", source=src_raw_segments, line_color=color_raw)

        p_tr.multi_line(xs="xs", ys="ys", source=src_tr_segments, line_color=color_trend)

        # Hovers (vline) – tooltips los van multi_line via slider-bronnen
        p_cent.add_tools(HoverTool(tooltips=[("Time","$x{0.0000}"),("Centroid","$y{0.000000}")],
                           mode="vline"))
        p_raw.add_tools(HoverTool(tooltips=[("Time","$x{0.0000}"),("Raw flux","$y{0.000000}")],
                                mode="vline"))
        p_tr.add_tools(HoverTool(tooltips=[("Time","$x{0.0000}"),("Trend","$y{0.000000}")],
                                mode="vline"))


        # ---------- VERTICAL SPANS + SLIDER ----------
        # Start op min van alle tijdreeksen
        all_mins = [a.min() for a in [flat_cent_t, flat_raw_t, flat_tr_t] if a.size]
        all_maxs = [a.max() for a in [flat_cent_t, flat_raw_t, flat_tr_t] if a.size]
        t_min = float(np.nanmin(all_mins)) if all_mins else 0.0
        t_max = float(np.nanmax(all_maxs)) if all_maxs else 1.0

        span_cent = Span(location=t_min, dimension="height", line_color="firebrick", line_width=2)
        span_raw  = Span(location=t_min, dimension="height", line_color="firebrick", line_width=2)
        span_tr   = Span(location=t_min, dimension="height", line_color="firebrick", line_width=2)

        p_cent.add_layout(span_cent)
        p_raw.add_layout(span_raw)
        p_tr.add_layout(span_tr)

        slider = Slider(start=t_min, end=t_max, value=t_min, step=step, title="Select time (BTJD)")
        info_div = Div(text=f"t = {t_min:.4f}", width=400)

        # Eén callback die alle drie de spans + readouts bijwerkt
        callback = CustomJS(args=dict(
            s_cent=src_cent_pts, s_raw=src_raw_pts, s_tr=src_tr_pts,
            sp_cent=span_cent, sp_raw=span_raw, sp_tr=span_tr,
            div=info_div
        ), code="""
            const val = cb_obj.value;
            sp_cent.location = val;
            sp_raw.location  = val;
            sp_tr.location   = val;

            function nearestY(src, x) {
                const t = src.data.time;
                const y = src.data.y;
                if (!t || t.length === 0) { return NaN; }
                // binaire zoekopdracht
                let lo = 0, hi = t.length - 1;
                while (lo < hi) {
                    const mid = Math.floor((lo + hi)/2);
                    if (t[mid] < x) lo = mid + 1; else hi = mid;
                }
                let idx = lo;
                if (lo > 0 && Math.abs(t[lo-1]-x) <= Math.abs(t[lo]-x)) idx = lo-1;
                return y[idx];
            }

            const yc = nearestY(s_cent, val);
            const yr = nearestY(s_raw,  val);
            const yt = nearestY(s_tr,   val);

            div.text = `t = ${val.toFixed(4)} — centroid: ${Number.isFinite(yc)?yc.toFixed(6):'NA'} • raw: ${Number.isFinite(yr)?yr.toFixed(6):'NA'} • trend: ${Number.isFinite(yt)?yt.toFixed(6):'NA'}`;
        """)
        slider.js_on_change("value", callback)

        layout = column(p_cent, p_raw, p_tr, slider, info_div)
        show(layout)
        return layout

    info.plot_tripanel = MethodType(plot_tripanel, info)
    return info
