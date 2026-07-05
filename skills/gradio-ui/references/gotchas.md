# Gradio table gotchas — symptom → cause → fix

A debugging index for table rendering bugs. Only the non-obvious ones — for
anything that's plain in the docs, read the docs (see the pointer table in
SKILL.md). Match your symptom, apply the fix, then verify in the browser.

## Styling missing or lost

- **Colors/bars/formatting don't show at all.** → Table is interactive (styling
  only works when static). Often because it's used as an event **input**. → Set
  `interactive=False` explicitly.
- **Styling shows on load, disappears after a filter/refresh.** → Update returned
  a bare DataFrame or reused the old Styler (a Styler is a snapshot). → Rebuild
  `df.style…` on the new data; return `gr.update(value=new_styler, …)`.
- **Header row won't take a background color.** → Styler can't reach headers. →
  Position CSS (`#elem-id th:nth-child(n) … !important`) via a `gr.HTML`,
  regenerated when columns change. Snippet in SKILL.md.
- **`Styler.hide()` doesn't drop the column.** → Known limitation, gradio issue
  #9714. → `df.drop(columns=…)` before styling.

## Colors look wrong

- **Bar lengths / gradient shades jump between renders.** → No fixed scale, so it
  renormalizes to the visible rows. → Pass explicit `vmin`/`vmax` to
  `.bar` / `.background_gradient`.

## Columns render as the wrong type

- **A link column shows raw `[text](url)`.** → That column isn't `"markdown"` in
  `datatype`. → Set it.
- **After filtering columns, types/links misalign.** → `datatype` is positional
  and still matches the old column set. → Recompute it from the new visible
  columns and send it in the same `gr.update(value=…, datatype=…)`.

## Filtering misbehaves

- **Filters only ever narrow; unchecking doesn't bring rows back.** → Filtering
  the already-filtered displayed table. → Hold the full df in `gr.State`, filter
  from it (copy first).
- **`TypeError` on args, or the wrong component updates.** → Handler params don't
  match `inputs` order, or return count ≠ `outputs` count. → Line them up;
  `@gr.on(triggers=[…])` keeps multi-control wiring in sync.
- **Empty selection shows everything (or errors).** → Unhandled empty value. →
  Decide explicitly, e.g. `df.iloc[0:0]` for "nothing selected → empty".

## Version / API drift (Gradio 6)

- **`show_copy_button` / `show_fullscreen_button` do nothing.** → v5 params. →
  `buttons=["copy", "fullscreen"]`.
- **`col_count` deprecation warning.** → `column_count`.
- **A copied snippet fights the installed API.** → Most online Dataframe examples
  predate the v6 rework. → `python -c "import gradio, inspect;
  print(inspect.signature(gradio.Dataframe.__init__))"` and trust that.

## Layout / performance

- **Table absurdly tall.** → Set `max_height` (default 500) and/or `wrap=True`
  with `column_widths`.
- **Important columns scroll out of view on wide tables.** → `pinned_columns=N`
  (verify visually — pin + custom widths + wrap can interact oddly).
- **Janky on every keystroke.** → Heavy work (network/disk/full re-style) on
  `.change` of a fast control. → Move heavy reloads to a button; use `gr.Timer` /
  `every=` for periodic refresh.

## Components not appearing

- **`AttributeError` / component missing.** → Created outside `with gr.Blocks()`.
  → Build everything (including `gr.State`) inside the context.
