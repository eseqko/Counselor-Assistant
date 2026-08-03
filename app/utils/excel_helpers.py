"""Shared builder for the data-import Excel templates.

The three templates (attendance, grades, student-update) all share the same
header style, instructions sheet pattern, and freeze-panes setup. They differ
only in the columns, validations, optional pre-filled rows, and whether the
first column gets a locked-key tint.
"""
import io
from flask import send_file
from app.utils.security import xlsx_safe


# Late-imported by callers via app.routes.data_import; we accept the openpyxl
# objects as parameters so this helper has zero hard dependency on openpyxl.
# Callers pass them in once at the top of the route module.

HEADER_FILL_HEX = '2C5F8A'
INSTRUCTIONS_TAB_HEX = 'E8A838'
LOCK_FILL_HEX = 'F0F0F0'
TITLE_COLOR_HEX = '2C5F8A'


def build_import_workbook(
    openpyxl_kit,
    *,
    sheet_title,
    columns,
    instructions,
    validations=None,
    prefill_rows=None,
    lock_first_column=False,
    header_wrap=False,
    instructions_col_widths=(18, 75),
):
    """Build a styled import workbook and return it ready for caller to save.

    openpyxl_kit: dict with keys Workbook, Font, PatternFill, Alignment,
        Border, Side, get_column_letter, DataValidation. Pass the import
        names from the data_import package's openpyxl shim.
    sheet_title: str. Active sheet title.
    columns: list of (header_text, column_width) tuples for the data sheet.
    instructions: list of (col_a, col_b) tuples for the Instructions sheet.
        First row is rendered as a 14pt title.
    validations: optional list of dicts:
        {'type': 'list', 'formula1': '"a,b,c"', 'sqref': 'D2:D5000',
         'allow_blank': True, 'error_title': '...', 'error_message': '...'}
    prefill_rows: optional list-of-lists with row data starting at row 2.
    lock_first_column: if True and prefill_rows is set, gray-fill the first
        column on data rows to indicate it's a read-only matching key.
    header_wrap: if True, wrap text in header cells.
    """
    Workbook = openpyxl_kit['Workbook']
    Font = openpyxl_kit['Font']
    PatternFill = openpyxl_kit['PatternFill']
    Alignment = openpyxl_kit['Alignment']
    Border = openpyxl_kit['Border']
    Side = openpyxl_kit['Side']
    get_column_letter = openpyxl_kit['get_column_letter']
    DataValidation = openpyxl_kit['DataValidation']

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    header_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color=HEADER_FILL_HEX,
                              end_color=HEADER_FILL_HEX, fill_type='solid')
    thin = Side(style='thin')
    thin_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_alignment = Alignment(horizontal='center', vertical='center',
                                 wrap_text=header_wrap)

    # Header row
    for col_idx, (name, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Validations
    for v in (validations or []):
        dv_kwargs = {
            'type': v.get('type', 'list'),
            'formula1': v['formula1'],
            'allow_blank': v.get('allow_blank', True),
        }
        if v.get('error_title') or v.get('error_message'):
            dv_kwargs.update(
                showErrorMessage=True,
                errorTitle=v.get('error_title', 'Invalid'),
                error=v.get('error_message', 'Invalid value'),
            )
        dv = DataValidation(**dv_kwargs)
        dv.sqref = v['sqref']
        ws.add_data_validation(dv)

    # Prefill rows
    if prefill_rows:
        lock_fill = PatternFill(start_color=LOCK_FILL_HEX,
                                end_color=LOCK_FILL_HEX, fill_type='solid')
        for row_idx, row in enumerate(prefill_rows, start=2):
            for col_idx, val in enumerate(row, 1):
                # Shared by several exports; prefill values originate from
                # imported rosters, so neutralize formula triggers here once.
                cell = ws.cell(row=row_idx, column=col_idx, value=xlsx_safe(val))
                cell.border = thin_border
            if lock_first_column:
                ws.cell(row=row_idx, column=1).fill = lock_fill

    # Instructions sheet
    instr = wb.create_sheet('Instructions')
    instr.sheet_properties.tabColor = INSTRUCTIONS_TAB_HEX
    for row_idx, (a, b) in enumerate(instructions, 1):
        instr.cell(row=row_idx, column=1, value=a).font = Font(
            name='Calibri', bold=bool(a),
            size=14 if row_idx == 1 else 11,
            color=TITLE_COLOR_HEX if row_idx == 1 else '000000')
        instr.cell(row=row_idx, column=2, value=b).font = Font(
            name='Calibri', size=11)
    instr.column_dimensions['A'].width = instructions_col_widths[0]
    instr.column_dimensions['B'].width = instructions_col_widths[1]

    ws.freeze_panes = 'A2'
    return wb


def workbook_response(wb, filename):
    """Save workbook to BytesIO and return a Flask send_file response."""
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name=filename,
    )
