/**
 * RFC 4180 CSV building for spreadsheet export.
 *
 * - Every field is quoted only when needed, with embedded quotes doubled.
 * - Values that a spreadsheet would interpret as a formula (leading = + - @, tab or CR) are
 *   prefixed with an apostrophe so a student named `=HYPERLINK(...)` can't execute anything when
 *   the professor opens the file ("CSV injection").
 * - Output starts with a UTF-8 BOM so Excel reads non-ASCII names (Zoe with diaeresis, etc.) correctly,
 *   and uses CRLF line endings as the RFC specifies.
 */
const FORMULA_START = /^[=+\-@\t\r]/;

export function csvField(value: string | number | null | undefined): string {
  let text = value === null || value === undefined ? "" : String(value);
  // Numbers such as "-5" are harmless; only guard free text.
  if (typeof value !== "number" && FORMULA_START.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function buildCsv(rows: (string | number | null | undefined)[][]): string {
  return "\uFEFF" + rows.map((row) => row.map(csvField).join(",")).join("\r\n") + "\r\n";
}
