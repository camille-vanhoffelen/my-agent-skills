---
name: gradio-ui
description: >-
  Non-obvious knowledge for building and debugging Gradio UIs, especially data
  tables (gr.Dataframe): filtered leaderboards/dashboards, pandas Styler colors
  and formatting, per-column header coloring, in-cell bars, and the
  counterintuitive gotchas of the Gradio 6 DataFrame API that aren't obvious
  from the docs. Use this whenever working on a Gradio app (gr.Blocks,
  gr.Dataframe, gr.update, leaderboards, dashboards, filtered tables), when a
  Gradio table renders wrong (styling ignored, colors/bars missing, columns
  mistyped or misaligned, links shown as raw text, uncolored headers, filters
  that won't widen), or when wiring filters to a table — even if the user is
  just editing a Gradio app.py without naming Gradio. Reach for it before
  guessing from memory: the DataFrame API changed heavily in v5→v6 and most
  online/recalled advice is stale.
compatibility: Confirm the installed Gradio version before trusting version-specific details; the specifics here assume Gradio 6.x.
version: 1.0.0
---

# Gradio UIs, table-focused: what the docs won't tell you

You can already read the Gradio docs and source — so this skill deliberately
**does not restate the API**. It captures only what's expensive to discover:
counterintuitive behaviors, a couple of known bugs, and exactly which page or
object to inspect when you *do* need detail. When something here is
version-specific, trust the installed source over this file.

## Anchor to the installed version first

The table API changed a lot in Gradio 5→6, so much web/LLM-memory advice is
stale. Confirm what you're actually working with:

```bash
python -c "import gradio, inspect; print(gradio.__version__); print(inspect.signature(gradio.Dataframe.__init__))"
```

Prefer `inspect.signature` over a remembered parameter list. The specifics below
assume Gradio 6.x.

## Gotchas that burn hours (hard to infer from docs)

1. **Styling only survives on a *static* table.** A pandas `Styler` (colors,
   bars, number formatting) is honored **only when `interactive=False`**. A
   `gr.Dataframe` silently becomes interactive if you use it as an event
   **input** — and then all styling is dropped with at most a warning. Set
   `interactive=False` explicitly on any display table. This is the #1 "why are
   my colors gone."

2. **A Styler is a snapshot, not a binding.** To update a styled table, build a
   **fresh** `df.style…` on the new data and push
   `gr.update(value=new_styler, datatype=…)`. Returning a bare DataFrame, or
   reusing the old Styler, loses the styling.

3. **Headers can't be styled by the Styler.** Gradio renders the header row
   itself; cell colors work, header backgrounds don't. Color headers with
   position-based CSS instead (snippet below), regenerated when the visible
   columns change.

4. **`datatype` is a positional list that must track the visible columns.** It
   sets per-column rendering (`"markdown"` for links, `"number"`, `"str"`, …).
   Filter columns in/out without recomputing it and links render as raw text and
   columns get mistyped. Send it *with* the value: `gr.update(value=…,
   datatype=…)`.

5. **Bars/gradients renormalize per render.** Without explicit `vmin`/`vmax`,
   `.bar()` and `.background_gradient()` rescale to whatever rows are currently
   shown, so bars visibly jump when you filter. Pin `vmin`/`vmax`.

6. **`Styler.hide()` is unreliable in Gradio** (gradio issue #9714). Hide
   columns by dropping them from the DataFrame before building the Styler.

7. **Filters that only ever narrow** mean you're filtering the already-filtered
   *displayed* table. Hold the full DataFrame in a `gr.State` and always filter
   from it (copy first).

8. **v5→v6 renames that break copied snippets:**
   `show_copy_button` / `show_fullscreen_button` → `buttons=["copy",
   "fullscreen"]`; `col_count` → `column_count`. When a snippet fights the
   installed API, check the signature above rather than trusting the snippet.

## The one technique worth spelling out: header colors

Because the Styler can't reach headers, target them by 1-based position under the
table's `elem_id`, and regenerate the CSS whenever visible columns change (their
positions shift):

```python
def header_css(columns, groups):  # groups: list[(list[col_name], css_color)]
    pos = {c: i + 1 for i, c in enumerate(columns)}
    rules = [
        f'{", ".join(f"#my-table th:nth-child({pos[c]})" for c in cols if c in pos)}'
        f' {{ background-color: {color} !important; }}'
        for cols, color in groups if any(c in pos for c in cols)
    ]
    return f"<style>{''.join(rules)}</style>"
```

Render it in a sibling `gr.HTML` and return it alongside the table update from
every filter handler. `#elem-id th:nth-child(n)` + `!important` is what reliably
beats Gradio's own header styling.

## Where to look when you need real detail

Don't reconstruct these from memory — read the source:

| Need | Go to |
|---|---|
| `gr.Dataframe` params/events | `inspect.signature` (above) · https://gradio.app/docs/gradio/dataframe |
| Passing a Styler; the raw `metadata` styling/`display_value` dict for effects Styler can't express | https://gradio.app/guides/styling-the-gradio-dataframe |
| Filter/stats dashboard patterns (`gr.on`, filter → update) | https://gradio.app/guides/filters-tables-and-stats |
| pandas Styler methods — `.format`/`.bar`/`.background_gradient`/`.highlight_*`/`subset` | https://pandas.pydata.org/docs/user_guide/style.html |
| Custom CSS/JS in `gr.Blocks` (theme vars, `elem_id` targeting) | https://gradio.app/guides/custom-CSS-and-JS |
| Symptom → cause → fix catalog for table bugs | [references/gotchas.md](references/gotchas.md) |

## Verify visually — code that compiles can still render wrong

Every gotcha above surfaces only in the browser. After a change, launch the app
(`python app.py`, or `gradio app.py` for auto-reload) and look at the specific
thing you changed; use a `/run` or `/verify` skill if available. Report what you
observed, not just that it imports.
