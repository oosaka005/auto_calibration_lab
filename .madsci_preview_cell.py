# ---- Preview dispense repeatability plot with dummy data ----
import statistics
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

dummy_repeatability_result = {
    "material_name": "Siltech F-60,000",
    "pressure_mpa": 0.1,
    "target_masses_g": [0.010, 0.032, 0.100, 0.316, 1.000],
    "repeat_count": 3,
    "results": [
        {"target_mass_g": 0.010, "repeat_index": 1, "measured_mass_g": 0.0104, "elapsed_s": 12.1},
        {"target_mass_g": 0.010, "repeat_index": 2, "measured_mass_g": 0.0101, "elapsed_s": 11.8},
        {"target_mass_g": 0.010, "repeat_index": 3, "measured_mass_g": 0.0103, "elapsed_s": 12.0},
        {"target_mass_g": 0.032, "repeat_index": 1, "measured_mass_g": 0.0315, "elapsed_s": 12.9},
        {"target_mass_g": 0.032, "repeat_index": 2, "measured_mass_g": 0.0324, "elapsed_s": 12.7},
        {"target_mass_g": 0.032, "repeat_index": 3, "measured_mass_g": 0.0320, "elapsed_s": 12.8},
        {"target_mass_g": 0.100, "repeat_index": 1, "measured_mass_g": 0.1012, "elapsed_s": 14.1},
        {"target_mass_g": 0.100, "repeat_index": 2, "measured_mass_g": 0.0994, "elapsed_s": 13.9},
        {"target_mass_g": 0.100, "repeat_index": 3, "measured_mass_g": 0.1001, "elapsed_s": 14.0},
        {"target_mass_g": 0.316, "repeat_index": 1, "measured_mass_g": 0.3180, "elapsed_s": 17.2},
        {"target_mass_g": 0.316, "repeat_index": 2, "measured_mass_g": 0.3151, "elapsed_s": 17.0},
        {"target_mass_g": 0.316, "repeat_index": 3, "measured_mass_g": 0.3164, "elapsed_s": 17.1},
        {"target_mass_g": 1.000, "repeat_index": 1, "measured_mass_g": 1.0040, "elapsed_s": 24.5},
        {"target_mass_g": 1.000, "repeat_index": 2, "measured_mass_g": 0.9970, "elapsed_s": 24.2},
        {"target_mass_g": 1.000, "repeat_index": 3, "measured_mass_g": 1.0010, "elapsed_s": 24.4},
    ],
}

def preview_dispense_repeatability_plot(repeatability_result: dict):
    material_name = repeatability_result.get("material_name", "unknown")
    pressure_mpa = repeatability_result.get("pressure_mpa", "?")
    repeat_count = repeatability_result.get("repeat_count", "?")
    results = repeatability_result.get("results", [])
    target_masses = [float(v) for v in repeatability_result.get("target_masses_g", [])]
    grouped = {
        target: [
            r for r in results
            if float(r["target_mass_g"]) == target and r.get("measured_mass_g") is not None
        ]
        for target in target_masses
    }

    summary_rows = []
    raw_rows = []
    for target in target_masses:
        rows = grouped[target]
        masses = [float(r["measured_mass_g"]) for r in rows]
        mean_mass = statistics.fmean(masses)
        stdev_mass = statistics.stdev(masses) if len(masses) > 1 else 0.0
        error_percents = [(m - target) / target * 100.0 for m in masses]
        mean_error_pct = statistics.fmean(error_percents)
        cv_pct = stdev_mass / abs(mean_mass) * 100.0 if mean_mass != 0 else None
        elapsed_values = [float(r.get("elapsed_s", 0.0)) for r in rows if r.get("elapsed_s") is not None]
        mean_elapsed_s = statistics.fmean(elapsed_values) if elapsed_values else None
        summary_rows.append([
            f"{target:g}", str(len(masses)), f"{mean_mass:.5g}",
            f"{mean_error_pct:+.2f}", f"{cv_pct:.2f}" if cv_pct is not None else "n/a",
            f"{mean_elapsed_s:.1f}" if mean_elapsed_s is not None else "n/a",
        ])
        for r in rows:
            measured = float(r["measured_mass_g"])
            error_pct = (measured - target) / target * 100.0
            raw_rows.append([
                f"{target:g}", str(r.get("repeat_index", "")), f"{measured:.5g}",
                f"{error_pct:+.2f}", f"{float(r.get('elapsed_s', 0.0)):.1f}" if r.get("elapsed_s") is not None else "n/a",
            ])

    raw_table_height = max(1.6, 0.18 * (len(raw_rows) + 1))
    fig_height = min(18.0, max(10.0, 6.5 + raw_table_height))
    fig = plt.figure(figsize=(10, fig_height))
    gs = gridspec.GridSpec(3, 1, height_ratios=[4.0, 1.2, raw_table_height], hspace=0.45)

    ax = fig.add_subplot(gs[0])
    ax_error = ax.twinx()
    x_positions = np.arange(len(target_masses), dtype=float)
    max_repeats = max(len(grouped[target]) for target in target_masses)
    bar_width = min(0.18, 0.72 / max(max_repeats, 1))
    all_masses = [float(r["measured_mass_g"]) for target in target_masses for r in grouped[target]]
    mean_error_percents = []
    use_log_y = (
        all(m > 0 for m in all_masses + target_masses)
        and max(all_masses + target_masses) / min(all_masses + target_masses) > 20
    )
    bar_bottom = min(all_masses + target_masses) * 0.5 if use_log_y else 0.0

    for x_pos, target in zip(x_positions, target_masses):
        rows = sorted(grouped[target], key=lambda r: r.get("repeat_index", 0))
        masses = [float(r["measured_mass_g"]) for r in rows]
        offsets = (np.arange(len(masses)) - (len(masses) - 1) / 2.0) * bar_width
        ax.bar(
            x_pos + offsets, [m - bar_bottom for m in masses], width=bar_width * 0.88, bottom=bar_bottom,
            color="#6baed6", edgecolor="white", linewidth=0.8, alpha=0.9,
            label="Measured mass" if x_pos == 0 else None,
        )
        ax.hlines(
            target, x_pos - 0.42, x_pos + 0.42, color="#333333", linestyle="--", linewidth=1.8,
            zorder=4, label="Target mass" if x_pos == 0 else None,
        )
        mean_error_pct = statistics.fmean([(m - target) / target * 100.0 for m in masses])
        mean_error_percents.append(mean_error_pct)
        ax_error.plot(
            [x_pos], [mean_error_pct], color="#cc3311", marker="o", markersize=7,
            linestyle="None", zorder=6, label="Mean error [%]" if x_pos == 0 else None,
        )
        ax_error.annotate(
            f"{mean_error_pct:+.2f}%", xy=(x_pos, mean_error_pct), xytext=(6, 0),
            textcoords="offset points", va="center", ha="left", fontsize=8,
            color="#cc3311", zorder=7,
        )

    if use_log_y:
        ax.set_yscale("log")
    ax_error.axhline(0.0, color="#cc3311", linestyle="--", linewidth=1.0, alpha=0.5)
    max_abs_mean_error = max(abs(v) for v in mean_error_percents) if mean_error_percents else 1.0
    error_limit = max(1.0, max_abs_mean_error * 1.25)
    ax_error.set_ylim(-error_limit, error_limit)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([f"{target:g}" for target in target_masses])
    ax.set_xlabel("Target mass [g]", fontsize=11)
    ax.set_ylabel("Measured mass [g]", fontsize=11)
    ax_error.set_ylabel("Mean error [%]", fontsize=11, color="#cc3311")
    ax_error.tick_params(axis="y", colors="#cc3311")
    ax.set_title(f"Dispense Repeatability - {material_name} ({pressure_mpa} MPa, n={repeat_count})",
                 fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.25)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_error.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=9)

    ax_summary = fig.add_subplot(gs[1])
    ax_summary.axis("off")
    summary_labels = ["Target [g]", "n", "Mean measured [g]", "Mean error [%]", "CV [%]", "Avg time [s]"]
    summary_table = ax_summary.table(cellText=summary_rows, colLabels=summary_labels, loc="center", cellLoc="center")
    summary_table.auto_set_font_size(False)
    summary_table.set_fontsize(9)
    summary_table.scale(1, 1.4)
    for col in range(len(summary_labels)):
        summary_table[(0, col)].set_facecolor("#cce0ff")
        summary_table[(0, col)].set_text_props(fontweight="bold")

    ax_raw = fig.add_subplot(gs[2])
    ax_raw.axis("off")
    raw_labels = ["Target [g]", "Repeat", "Measured [g]", "Error [%]", "Time [s]"]
    raw_table = ax_raw.table(cellText=raw_rows, colLabels=raw_labels, loc="center", cellLoc="center")
    raw_table.auto_set_font_size(False)
    raw_table.set_fontsize(8 if len(raw_rows) <= 30 else 7)
    raw_table.scale(1, 1.2)
    for col in range(len(raw_labels)):
        raw_table[(0, col)].set_facecolor("#e6e6e6")
        raw_table[(0, col)].set_text_props(fontweight="bold")

    plt.show()

preview_dispense_repeatability_plot(dummy_repeatability_result)
