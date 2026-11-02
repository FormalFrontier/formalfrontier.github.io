# formalfrontier.github.io

The public dashboard of the [FormalFrontier](https://github.com/FormalFrontier)
Lean libraries, served at <https://formalfrontier.github.io>.

- **Overview**: totals and daily growth of the released libraries.
- **Dependency graph**: the libraries and the direct dependencies between them.
- **Highlights**: the headline results of each library, linked to their Lean code.
- **Libraries**: a sortable table with the size and history of every library.

## Data

Everything comes from public GitHub, without credentials beyond the workflow's
built-in token.

- A **library** is a public, non-archived, non-fork repository of the
  organization whose default branch has a `formalization.yaml`.
- A library's default branch is its release history: every first-parent commit
  is one **release**.
- **Lines of Lean** count every line of the `.lean` files in the latest release,
  comments and blank lines included.
- **Theorems and lemmas** and **definitions** count declarations by keyword
  (`theorem`/`lemma`; `def`, `abbrev`, `structure`, `class`, `inductive`,
  `instance`) in library code. Test and example directories are excluded.
- **Dependencies** are the direct packages in `lake-manifest.json` that point to
  another library of the organization.
- **Highlights** come from an optional `highlights` list in `formalization.yaml`
  when a library has one, and otherwise from the `## Headline results` section
  of its README.

`scripts/update.py` clones each library, computes these values and writes
`site/data`. The site itself is static HTML, CSS and JavaScript with no build
step and no third-party code.

## Updates

The [workflow](.github/workflows/update.yml) runs daily at 04:17 UTC, on every
push to `main` and on demand. It refreshes `site/data`, commits any change and
deploys `site/` to GitHub Pages.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install --no-deps --require-hashes -r requirements.txt
.venv/bin/python scripts/update.py          # writes site/data
python3 -m http.server --directory site 8000
```

`--offline` reuses the clones in `.cache/repos` without fetching.

## License

[Apache-2.0](LICENSE).
