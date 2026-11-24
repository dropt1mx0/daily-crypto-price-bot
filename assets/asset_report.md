# Supplied asset inspection

| File | Size | Mode | Alpha / background |
|---|---:|---|---|
| `template.png` | 1219 × 1280 | RGB | No alpha channel; orange banner background |
| `green_badge.png` | 1280 × 455 | RGB | No alpha channel; black matte at image edges |
| `red_badge.png` | 2103 × 748 | RGBA | Alpha channel ranges from 0 to 255 |

The original red and green files are retained here as source files, but the
current renderer does not place them in the banner. It draws softly shaded
rounded cells in code so the percentage, digits, and sign can share one font
size and style. All 11 supplied token logos are processed into round PNGs under
`token_logos/` and used in their corresponding table rows.
