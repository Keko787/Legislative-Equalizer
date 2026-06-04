-- Convert pandoc Table AST → raw LaTeX as `table*` + `tabular`, bypassing
-- longtable so the build succeeds inside a two-column document class.

local function cell_to_latex(cell)
  -- Use pandoc.write on the cell contents to get inline LaTeX (preserves
  -- emphasis, code, etc.). Trim trailing newline.
  local doc = pandoc.Pandoc(cell.contents)
  local s = pandoc.write(doc, 'latex')
  s = s:gsub("\n+$", "")
  return s
end

function Table(t)
  -- Build column spec: one 'l' per colspec, joined with no separators.
  local cols = ""
  for _ = 1, #t.colspecs do cols = cols .. "l" end

  -- Caption text (long form if present, else short).
  local caption_text = ""
  if t.caption and t.caption.long and #t.caption.long > 0 then
    caption_text = pandoc.write(pandoc.Pandoc(t.caption.long), 'latex')
    caption_text = caption_text:gsub("\n+$", "")
  end

  local out = {}
  table.insert(out, "\\begin{table*}[!t]")
  table.insert(out, "\\centering")
  if caption_text ~= "" then
    table.insert(out, "\\caption{" .. caption_text .. "}")
  end
  table.insert(out, "\\small")
  table.insert(out, "\\begin{tabular}{" .. cols .. "}")
  table.insert(out, "\\toprule")

  -- Header rows (bold).
  if t.head and t.head.rows then
    for _, row in ipairs(t.head.rows) do
      local cells = {}
      for _, c in ipairs(row.cells) do
        table.insert(cells, "\\textbf{" .. cell_to_latex(c) .. "}")
      end
      table.insert(out, table.concat(cells, " & ") .. " \\\\")
    end
    table.insert(out, "\\midrule")
  end

  -- Body rows.
  for _, body in ipairs(t.bodies) do
    for _, row in ipairs(body.body) do
      local cells = {}
      for _, c in ipairs(row.cells) do
        table.insert(cells, cell_to_latex(c))
      end
      table.insert(out, table.concat(cells, " & ") .. " \\\\")
    end
  end

  table.insert(out, "\\bottomrule")
  table.insert(out, "\\end{tabular}")
  table.insert(out, "\\end{table*}")

  return pandoc.RawBlock('latex', table.concat(out, "\n"))
end
