# ruff: noqa: E501 - SQL kept on the lines a reader runs it from
"""The gateway's SQL Server adapter on a real SQL Server 2017, end to end.

A throwaway container (`DW_BRAVO_TEST_MSSQL` = `host,port,sa-password`) and a
minimal schema written for this test in Bravo's names: no table, column or
row of Proterial's. It shows what only a running server can: the PIC's
context reaching a trigger under a login holding column grants only, the
rowversion condition refusing a stale row, `ufn_Prevent_Edit` locking a line,
`usp_sys_GetControlPermission` barring a column, and the layout read from
`B00LayoutData`. Skipped where no such server is given (CI has none); ticket
63's Comments record the run.
"""

from __future__ import annotations

import io
import os
import secrets
import zipfile
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Literal

import mssql_python
import pytest
from gateway_fakes import (
    LAYOUT,
    NOW,
    TENANT,
    TEST_SCREENS,
    VERIFIER,
    FakeLedger,
    FakeSwitches,
    token,
)

from dw_bravo.contract import LineRef, SetConfirmedDate, SetQuantity
from dw_bravo_gateway.adapters.sqlserver import Login, SqlServerBravo
from dw_bravo_gateway.pipeline import WritePace, WritePipeline
from dw_bravo_gateway.ports import AmbiguousDocumentError, CommandRight, DocumentNotFoundError

SERVER = os.environ.get("DW_BRAVO_TEST_MSSQL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not SERVER, reason="no throwaway SQL Server (DW_BRAVO_TEST_MSSQL)"),
]

DB = "BravoGatewayTest"


def _sa(database: str = "master") -> object:
    host, port, password = (SERVER or ",,").split(",", 2)
    return mssql_python.connect(
        f"Server={host},{port};Database={database};UID=sa;PWD={password};"
        "Encrypt=yes;TrustServerCertificate=yes",
        autocommit=True,
    )


def _run(database: str, *statements: str) -> None:
    connection = _sa(database)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    for statement in statements:
        cursor.execute(statement)
    connection.close()  # type: ignore[attr-defined]


SHARED = (
    "<root><DataSource><Tables><ParentTable><CommandValidators>"
    "<ModifyInactiveData><CommandName>Edit</CommandName><Expr>ISNULL(IsActive,1)=1</Expr></ModifyInactiveData>"
    "<CreateData><CommandName>New,NewAsCopy,Edit</CommandName><Expr>BRANCH('IsGroup')=0</Expr></CreateData>"
    "<ModifyCurrentData><CommandName>Edit,Save</CommandName><Expr>BranchCode=BRANCH()</Expr></ModifyCurrentData>"
    "</CommandValidators></ParentTable></Tables></DataSource></root>"
)

TEMPLATE = (
    "<root><Tables><BizDoc><Cols><DocDate>B</DocDate></Cols><txtRowRange>4</txtRowRange></BizDoc>"
    "<Detail><txtForeignKey>A</txtForeignKey><Cols><POLine>S</POLine></Cols></Detail>"
    "</Tables></root>"
)


def _zipped(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Xml", text)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def logins() -> tuple[Login, Login]:
    host, port, _ = (SERVER or ",,").split(",", 2)
    read_pw, write_pw = f"R{secrets.token_hex(12)}a!", f"W{secrets.token_hex(12)}a!"
    _run(
        "master",
        f"IF DB_ID('{DB}') IS NOT NULL BEGIN ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {DB}; END",
        f"CREATE DATABASE {DB}",
        f"ALTER DATABASE {DB} SET ALLOW_SNAPSHOT_ISOLATION ON",
        "IF SUSER_ID('dw_test_read') IS NOT NULL DROP LOGIN dw_test_read",
        "IF SUSER_ID('dw_test_write') IS NOT NULL DROP LOGIN dw_test_write",
        f"CREATE LOGIN dw_test_read WITH PASSWORD = '{read_pw}', CHECK_POLICY = OFF",
        f"CREATE LOGIN dw_test_write WITH PASSWORD = '{write_pw}', CHECK_POLICY = OFF",
    )
    _run(
        DB,
        "CREATE TABLE dbo.B00UserList (Id int PRIMARY KEY, ParentId int, IsGroup bit,"
        " UserName varchar(24), Ma_CbNv varchar(24), Expire tinyint, IsActive bit)",
        "INSERT INTO dbo.B00UserList VALUES (2413, NULL, 0, 'pic', 'NV001', NULL, 1),"
        " (2414, NULL, 0, 'old', 'NV001', NULL, 0), (2415, NULL, 0, 'exp', 'NV002', 1, 1)",
        "CREATE TABLE dbo.B30BizDoc (Id int IDENTITY PRIMARY KEY, BizDocId varchar(16),"
        " DocCode char(2) DEFAULT 'SO', DocNo nvarchar(32) DEFAULT '',"
        " CustomerCode varchar(24) DEFAULT 'FG1', POCustomer nvarchar(192) DEFAULT 'PO-1',"
        " BranchCode varchar(3), DocDate datetime, TotalQuantity numeric(18,4), ModifiedBy int,"
        " ModifiedAt datetime DEFAULT GETDATE(), IsActive bit NOT NULL DEFAULT 1,"
        " timestamp rowversion)",
        # The branches, as `B00Branch` holds them: what `BRANCH('IsGroup')` reads.
        "CREATE TABLE dbo.B00Branch (Id int IDENTITY PRIMARY KEY, BranchCode varchar(3),"
        " IsGroup bit NOT NULL, IsActive bit NOT NULL)",
        "INSERT INTO dbo.B00Branch (BranchCode, IsGroup, IsActive) VALUES ('A01', 0, 1), ('A00', 1, 1)",
        "CREATE TABLE dbo.B30BizDocDetailSO (Id int IDENTITY PRIMARY KEY, BizDocId varchar(16),"
        " RowId varchar(16), BuiltinOrder smallint, POLine numeric(18,0) DEFAULT 0,"
        " ItemCode varchar(24) DEFAULT '', PORequestDate date, Quantity9 numeric(18,4),"
        " OriginalUnitCost numeric(18,4), Amount9 numeric(18,4), Made numeric(18,4),"
        " EstimatedTimeDelivery datetime, ModifiedBy int, ModifiedAt datetime DEFAULT GETDATE(),"
        " timestamp rowversion)",
        "CREATE TABLE dbo.ChangeLog (Id int IDENTITY PRIMARY KEY, RowId int, UserId int)",
        "CREATE TABLE dbo.Rights (UserId int, TableName varchar(48), ColumnName varchar(48),"
        " NoAddNew tinyint, NoEdit tinyint)",
        "CREATE TABLE dbo.B00Layout (Id int PRIMARY KEY, IsTemplate tinyint, FormName varchar(64), ModifiedBy int DEFAULT 1, ModifiedAt smalldatetime DEFAULT GETDATE(),"
        " IsActive bit)",
        "CREATE TABLE dbo.B00LayoutData (Id int PRIMARY KEY, LayoutData varbinary(max))",
        # One of ticket 50's tables, with a column the sync does not read.
        "CREATE TABLE dbo.B20LME (Id int IDENTITY PRIMARY KEY, IsGroup bit DEFAULT 0,"
        " BranchCode nvarchar(3) DEFAULT 'A01', Code varchar(24), Name nvarchar(64),"
        " Name2 nvarchar(64) DEFAULT 'not read', DocDate smalldatetime,"
        " LMEActual numeric(18,2), LMECenter numeric(18,2), IsActive bit DEFAULT 1,"
        " timestamp rowversion)",
        "INSERT INTO dbo.B20LME (Code, Name, DocDate, LMEActual, LMECenter) VALUES"
        " ('L1', N'Đồng', '2026-11-01', 9123.50, 9100.00), ('L2', N'Nhôm', '2026-11-02', 2500.10, 2490.00)",
        "CREATE TABLE dbo.B00ImportSetting (Id int PRIMARY KEY, CommandKey varchar(24),"
        " IsActive bit, LayoutData varbinary(8000))",
        "CREATE FUNCTION dbo.ufn_sys_GetUserIdFromContext_Info (@_ci varbinary(512)) RETURNS int AS"
        " BEGIN DECLARE @c varchar(512) = CAST(@_ci AS varchar(512)); DECLARE @p int = CHARINDEX('@', @c);"
        " IF @p <= 0 RETURN -1; SET @c = STUFF(@c, 1, @p, ''); SET @p = CHARINDEX('@', @c);"
        " IF @p <= 0 RETURN -1; RETURN CAST(LEFT(@c, @p - 1) AS int) END",
        "CREATE TRIGGER dbo.DML_B30BizDocDetailSO_ChangeLog ON dbo.B30BizDocDetailSO AFTER UPDATE AS"
        " INSERT INTO dbo.ChangeLog (RowId, UserId)"
        " SELECT Id, dbo.ufn_sys_GetUserIdFromContext_Info(CONTEXT_INFO()) FROM inserted",
        "CREATE FUNCTION dbo.ufn_Prevent_Edit (@_BizDocId varchar(16) = '', @_RowId varchar(16) = '',"
        " @_DocCode varchar(2) = 'SO') RETURNS int AS"
        " BEGIN RETURN CASE WHEN @_RowId = 'LOCKED' THEN 1 ELSE 0 END END",
        "CREATE FUNCTION dbo.ufn_B00Permission_Getdata (@_UserId int, @_RoleId int,"
        " @_PermissionType char(1)) RETURNS TABLE AS RETURN SELECT 1 AS NoEdit",
        "CREATE FUNCTION dbo.ufn_sys_GetPermissionUserListTable (@_UserId int)"
        " RETURNS TABLE AS RETURN SELECT @_UserId AS UserId",
        "CREATE TABLE dbo.B00Command (Id int PRIMARY KEY, CommandKey varchar(24), DLLName varchar(64),"
        " ClassName varchar(64), CtorArgs nvarchar(max), MethodName varchar(64), InvokeArgs nvarchar(max))",
        "INSERT INTO dbo.B00Command VALUES (1, 'EDIT_BizDocSO', 'Bravo.dll', 'DataEditor', N'x', NULL, NULL)",
        "CREATE PROCEDURE dbo.usp_sys_GetControlPermission @_UserId int, @_CommandKey varchar(24) AS"
        " SELECT TableName, ColumnName, NoAddNew, NoEdit FROM dbo.Rights WHERE UserId = @_UserId",
        "INSERT INTO dbo.B30BizDoc (BizDocId, DocNo, BranchCode, DocDate, TotalQuantity,"
        f" ModifiedBy) VALUES ('D1', 'SO-1', 'A01', '{NOW.year}-11-20', 3, 1)",
        "INSERT INTO dbo.B30BizDocDetailSO (BizDocId, RowId, BuiltinOrder, POLine, ItemCode,"
        " Quantity9, OriginalUnitCost, Amount9, Made, ModifiedBy, EstimatedTimeDelivery) VALUES"
        " ('D1', 'R1', 1, 1, 'PRV-1', 3, 2, 6, 2, 1, '2026-12-01'),"
        " ('D1', 'LOCKED', 2, 2, 'PRV-2', 1, 2, 2, 0, 1, NULL)",
        # Another document type under the same number, and one SO number twice.
        "INSERT INTO dbo.B30BizDoc (BizDocId, DocCode, DocNo, BranchCode, DocDate, TotalQuantity,"
        " ModifiedBy) VALUES ('P1', 'PO', 'SO-1', 'A01', '2026-11-20', 0, 1),"
        " ('D2', 'SO', 'SO-DUP', 'A01', '2026-11-20', 0, 1),"
        " ('D3', 'SO', 'SO-DUP', 'A02', '2026-11-20', 0, 1)",
        # A line under the PO document, which is not an SO.
        "INSERT INTO dbo.B30BizDocDetailSO (BizDocId, RowId, BuiltinOrder, POLine, ItemCode,"
        " Quantity9, OriginalUnitCost, Amount9, Made, ModifiedBy) VALUES"
        " ('P1', 'PR1', 1, 9, 'PO-ITEM', 1, 1, 1, 0, 1)",
        "CREATE USER dw_test_read FOR LOGIN dw_test_read",
        "CREATE USER dw_test_write FOR LOGIN dw_test_write",
        "GRANT SELECT ON dbo.B00UserList (Id, IsGroup, UserName, Ma_CbNv, Expire, IsActive) TO dw_test_read",
        "GRANT SELECT ON dbo.B30BizDoc TO dw_test_read",
        "GRANT SELECT ON dbo.B30BizDocDetailSO TO dw_test_read",
        "GRANT SELECT ON dbo.B00Layout TO dw_test_read",
        "GRANT SELECT ON dbo.B00Branch (BranchCode, IsGroup, IsActive) TO dw_test_read",
        "GRANT SELECT ON dbo.B00LayoutData TO dw_test_read",
        "GRANT SELECT ON dbo.B20LME (Id, timestamp, IsGroup, BranchCode, Code, Name, DocDate,"
        " LMEActual, LMECenter, IsActive) TO dw_test_read",
        "GRANT SELECT ON dbo.B00ImportSetting (Id, CommandKey, IsActive, LayoutData) TO dw_test_read",
        "GRANT EXECUTE ON dbo.usp_sys_GetControlPermission TO dw_test_read",
        "GRANT EXECUTE ON dbo.ufn_Prevent_Edit TO dw_test_read",
        "GRANT SELECT ON dbo.B00Command TO dw_test_read",
        *(
            f"GRANT VIEW DEFINITION ON dbo.{name} TO dw_test_read"
            for name in (
                "ufn_sys_GetUserIdFromContext_Info",
                "usp_sys_GetControlPermission",
                "ufn_B00Permission_Getdata",
                "ufn_sys_GetPermissionUserListTable",
                "ufn_Prevent_Edit",
            )
        ),
        "GRANT VIEW DEFINITION ON dbo.B30BizDoc TO dw_test_read",
        "GRANT VIEW DEFINITION ON dbo.B30BizDocDetailSO TO dw_test_read",
        # The write login: the columns the writes touch, and the WHERE's.
        "GRANT SELECT ON dbo.B30BizDoc (Id, timestamp) TO dw_test_write",
        "GRANT SELECT ON dbo.B30BizDocDetailSO (Id, timestamp) TO dw_test_write",
        "GRANT UPDATE ON dbo.B30BizDoc (TotalQuantity, ModifiedBy, ModifiedAt) TO dw_test_write",
        "GRANT UPDATE ON dbo.B30BizDocDetailSO (Quantity9, Amount9, EstimatedTimeDelivery,"
        " ModifiedBy, ModifiedAt) TO dw_test_write",
    )
    connection = _sa(DB)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    cursor.execute(
        "INSERT INTO dbo.B00Layout (Id, IsTemplate, FormName, IsActive) VALUES (1, 0, 'EDIT_BizDocSO', 1)"
    )
    cursor.execute("INSERT INTO dbo.B00LayoutData VALUES (1, ?)", (_zipped(LAYOUT),))
    cursor.execute(
        "INSERT INTO dbo.B00ImportSetting VALUES (7, 'EDIT_BizDocSO', 1, ?)", (_zipped(TEMPLATE),)
    )
    # The shared template the SO screen loads (script 03c's shape).
    cursor.execute(
        "INSERT INTO dbo.B00Layout (Id, IsTemplate, FormName, IsActive) VALUES (9, 1, 'BizDocEditor', 1)"
    )
    cursor.execute("INSERT INTO dbo.B00LayoutData VALUES (9, ?)", (_zipped(SHARED),))
    connection.close()  # type: ignore[attr-defined]
    return (
        Login(host, int(port), DB, "dw_test_read", read_pw),
        Login(host, int(port), DB, "dw_test_write", write_pw),
    )


class _Allowed(SqlServerBravo):
    """The live command right is unmeasured and answers "unknown"; these
    tests take it as allowed to reach the checks after it."""

    async def command_right(
        self, user_id: int, command_key: str, operation: Literal["update", "insert"]
    ) -> CommandRight:
        return "allowed"


def _pipeline(bravo: SqlServerBravo) -> WritePipeline:
    return WritePipeline(
        verifier=VERIFIER,
        switches=FakeSwitches(),
        ledger=FakeLedger(),
        directory=bravo,
        rights=bravo,
        documents=bravo,
        engine=bravo,
        writer=bravo,
        now=lambda: NOW,
        tenant_id=TENANT,
        screens=TEST_SCREENS,
        pace=WritePace(),
    )


async def _line(bravo: SqlServerBravo, row_id: str) -> LineRef:
    document = await bravo.load("EDIT_BizDocSO", 1)
    line = next(x for x in document.lines if x["RowId"] == row_id)
    return LineRef(so_id=1, line_id=int(line["Id"]), line_rowversion=str(line["timestamp"]))  # type: ignore[call-overload]


def _logged_users() -> list[int]:
    connection = _sa(DB)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("SELECT UserId FROM dbo.ChangeLog ORDER BY Id")
    users = [row[0] for row in cursor.fetchall()]
    connection.close()  # type: ignore[attr-defined]
    return users


async def test_the_pics_write_under_column_grants_reaches_bravos_trigger(
    logins: tuple[Login, Login],
) -> None:
    bravo = _Allowed(*logins, templates={})
    command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(5))

    result = await _pipeline(bravo).execute(command, token(command))

    assert result.outcome == "written", result
    after = await bravo.load("EDIT_BizDocSO", 1)
    line = next(x for x in after.lines if x["RowId"] == "R1")
    assert (line["Quantity9"], line["Amount9"], line["ModifiedBy"]) == (5, 10, 2413)
    assert after.header["TotalQuantity"] == 6
    assert _logged_users()[-1] == 2413  # the trigger read the PIC from the context


async def test_a_stale_line_is_refused_by_the_rowversion(logins: tuple[Login, Login]) -> None:
    bravo = _Allowed(*logins, templates={})
    approved = SetConfirmedDate(line=await _line(bravo, "R1"), confirmed_date=date(2026, 12, 1))
    _run(DB, "UPDATE dbo.B30BizDocDetailSO SET Made = Made WHERE RowId = 'R1'")  # a colleague saved

    result = await _pipeline(bravo).execute(approved, token(approved))

    assert (result.check, result.reason) == ("rules", "line_changed_since_approval")


async def test_a_line_on_a_cdo_is_locked_by_bravos_function(logins: tuple[Login, Login]) -> None:
    bravo = _Allowed(*logins, templates={})
    command = SetConfirmedDate(line=await _line(bravo, "LOCKED"), confirmed_date=date(2026, 12, 1))

    result = await _pipeline(bravo).execute(command, token(command))

    assert (result.check, result.reason) == ("lock", "line_locked_or_could_not_check")


async def test_a_column_bravo_bars_the_user_from_is_refused(logins: tuple[Login, Login]) -> None:
    _run(
        DB,
        "INSERT INTO dbo.Rights VALUES (2413, 'B30BizDocDetailSO', 'EstimatedTimeDelivery', 0, 1)",
    )
    bravo = _Allowed(*logins, templates={})
    command = SetConfirmedDate(line=await _line(bravo, "R1"), confirmed_date=date(2026, 12, 1))
    try:
        result = await _pipeline(bravo).execute(command, token(command))
    finally:
        _run(DB, "DELETE FROM dbo.Rights")

    assert (result.check, result.reason) == ("right", "no_right_on_EstimatedTimeDelivery")


async def test_the_live_command_right_is_unmeasured_and_refuses(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins, templates={})
    command = SetConfirmedDate(line=await _line(bravo, "R1"), confirmed_date=date(2026, 12, 1))

    result = await _pipeline(bravo).execute(command, token(command))

    assert (result.check, result.reason) == ("right", "command_right_unknown")


async def test_identity_reads_one_active_user_per_employee_code(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins)

    users = await bravo.users_by_employee_code("NV001")
    expired = await bravo.users_by_employee_code("NV002")

    assert sorted((u.id, u.active) for u in users) == [(2413, True), (2414, False)]
    assert [(u.id, u.active) for u in expired] == [(2415, False)]


async def test_an_so_is_read_by_its_number_in_the_clients_line_order(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins)

    so = await bravo.sales_order("SO-1")

    assert so.so_no == "SO-1"
    # Line 1's quantity is whatever an earlier test of this module wrote.
    assert [(x.po_line, x.item_code, x.confirmed_date) for x in so.lines] == [
        (1, "PRV-1", date(2026, 12, 1)),
        (2, "PRV-2", None),
    ]
    assert so.lines[1].quantity == Decimal(1)
    assert all(x.rowversion.startswith("0x") and len(x.rowversion) == 18 for x in so.lines)
    with pytest.raises(DocumentNotFoundError):
        await bravo.sales_order("SO-404")
    with pytest.raises(AmbiguousDocumentError):
        await bravo.sales_order("SO-DUP")


async def test_a_customers_po_reads_every_so_line_with_its_price(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins)

    found = await bravo.customer_po("FG1", "PO-1")

    # SO-1's two lines; SO-DUP's headers carry no line; the PO document is not an SO.
    assert [(r.so_no, r.po_line, r.item_code, r.unit_price) for r in found.rows] == [
        ("SO-1", 1, "PRV-1", Decimal(2)),
        ("SO-1", 2, "PRV-2", Decimal(2)),
    ]
    assert found.rows[0].confirmed_date == date(2026, 12, 1)
    assert (await bravo.customer_po("FG2", "PO-1")).rows == ()


async def test_the_write_login_cannot_touch_a_column_it_was_not_granted(
    logins: tuple[Login, Login],
) -> None:
    _, write = logins
    connection = mssql_python.connect(write.connection_string(), autocommit=True)
    cursor = connection.cursor()
    with pytest.raises(Exception, match="permission was denied"):
        cursor.execute("UPDATE dbo.B30BizDocDetailSO SET Made = 0 WHERE Id = 1")
    connection.close()


async def test_a_wrong_password_is_bravo_not_answering(logins: tuple[Login, Login]) -> None:
    read, write = logins
    bravo = SqlServerBravo(replace(read, password="wrong"), write)
    command = SetConfirmedDate(
        line=LineRef(so_id=1, line_id=1, line_rowversion="0x0000000000000001"),
        confirmed_date=date(2026, 12, 1),
    )

    result = await _pipeline(bravo).execute(command, token(command))

    assert (result.outcome, result.reason) == ("refused", "bravo_unreachable_could_not_check")


async def test_the_shipped_adapter_reads_bizdoceditor_and_writes_under_its_guards(
    logins: tuple[Login, Login],
) -> None:
    """The shipped default names the SO screen's template; with it in Bravo
    (script 03c), the plan is complete and the write passes its guards."""
    bravo = _Allowed(*logins)
    command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(4))

    result = await _pipeline(bravo).execute(command, token(command))

    assert result.outcome == "written", result


async def test_a_row_saved_between_the_read_and_the_write_writes_nothing(
    logins: tuple[Login, Login],
) -> None:
    from dw_bravo_gateway.ports import Batch, StaleRowError
    from dw_bravo_gateway.statements import context_line, render_update

    bravo = SqlServerBravo(*logins, templates={})
    document = await bravo.load("EDIT_BizDocSO", 1)
    line = next(x for x in document.lines if x["RowId"] == "R1")
    _run(DB, "UPDATE dbo.B30BizDocDetailSO SET Made = Made WHERE RowId = 'R1'")  # the race
    statement = render_update(
        "B30BizDocDetailSO",
        {"Quantity9": Decimal(9), "ModifiedBy": 2413},
        document.column_order["B30BizDocDetailSO"],
        row_id=line["Id"],
        rowversion=str(line["timestamp"]),
        read_back_key="RowId",
    )
    batch = Batch(context_line("EDIT_BizDocSO", "Edit", 2413, "A01", NOW.year), [statement])

    with pytest.raises(StaleRowError):
        await bravo.execute(batch)

    after = await bravo.load("EDIT_BizDocSO", 1)
    assert next(x for x in after.lines if x["RowId"] == "R1")["Quantity9"] != 9


async def test_two_active_layouts_for_the_screen_refuse_rather_than_pick_one(
    logins: tuple[Login, Login],
) -> None:
    connection = _sa(DB)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    cursor.execute(
        "INSERT INTO dbo.B00Layout (Id, IsTemplate, FormName, IsActive) VALUES (2, 0, 'EDIT_BizDocSO', 1)"
    )
    cursor.execute("INSERT INTO dbo.B00LayoutData VALUES (2, ?)", (_zipped(LAYOUT),))
    connection.close()  # type: ignore[attr-defined]
    bravo = _Allowed(*logins, templates={})
    command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(4))
    try:
        result = await _pipeline(bravo).execute(command, token(command))
    finally:
        _run(
            DB,
            "DELETE FROM dbo.B00LayoutData WHERE Id = 2",
            "DELETE FROM dbo.B00Layout WHERE Id = 2",
        )

    assert result.check == "rules" and (result.reason or "").startswith("layout_could_not_be_read")


async def test_the_fingerprint_sees_a_trigger_and_a_column_change(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins)
    before = await bravo.fingerprint("production")
    kinds = {(c.kind, c.name) for c in before.components}
    assert ("trigger", "DML_B30BizDocDetailSO_ChangeLog") in kinds
    assert ("context_parser", "ufn_sys_GetUserIdFromContext_Info") in kinds
    assert ("layout", "EDIT_BizDocSO") in kinds and ("command", "EDIT_BizDocSO") in kinds

    _run(DB, "ALTER TABLE dbo.B30BizDocDetailSO ADD Measured int NULL")
    _run(DB, "DISABLE TRIGGER dbo.DML_B30BizDocDetailSO_ChangeLog ON dbo.B30BizDocDetailSO")
    try:
        after = await bravo.fingerprint("production")
    finally:
        _run(DB, "ENABLE TRIGGER dbo.DML_B30BizDocDetailSO_ChangeLog ON dbo.B30BizDocDetailSO")
        _run(DB, "ALTER TABLE dbo.B30BizDocDetailSO DROP COLUMN Measured")

    from dw_bravo.watch import diff, react

    changed = {(c.kind, c.name) for c in diff(before, after)}
    assert changed == {
        ("columns", "B30BizDocDetailSO"),
        ("trigger", "DML_B30BizDocDetailSO_ChangeLog"),
    }
    assert react(diff(before, after), {}).paused  # the dependent kinds pause


async def test_the_fingerprint_sees_an_import_template_change_and_names_one_it_cannot_read(
    logins: tuple[Login, Login],
) -> None:
    bravo = SqlServerBravo(*logins)
    before = await bravo.fingerprint("production")
    [template] = [c for c in before.components if c.kind == "template"]
    assert template.name == "EDIT_BizDocSO" and template.unknown == ()

    moved = TEMPLATE.replace("<POLine>S</POLine>", "<POLine>T</POLine>")
    connection = _sa(DB)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("UPDATE dbo.B00ImportSetting SET LayoutData = ? WHERE Id = 7", (_zipped(moved),))
    cursor.execute(
        "INSERT INTO dbo.B00ImportSetting VALUES (8, 'EDIT_BizDocSO', 1, ?)",
        (_zipped("<root><Tables><Detail><Formula>x</Formula></Detail></Tables></root>"),),
    )
    try:
        after = await bravo.fingerprint("production")
    finally:
        cursor.execute("DELETE FROM dbo.B00ImportSetting WHERE Id = 8")
        cursor.execute(
            "UPDATE dbo.B00ImportSetting SET LayoutData = ? WHERE Id = 7", (_zipped(TEMPLATE),)
        )
        connection.close()  # type: ignore[attr-defined]

    from dw_bravo.watch import diff, react

    [changed] = [c for c in diff(before, after) if c.kind == "template"]
    assert changed.after is not None and changed.after.unknown[0].startswith("template 8")
    assert "so.create@1" in react(diff(before, after), {}).paused


async def test_the_copy_reads_allowlisted_columns_in_rowversion_order_from_a_cursor(
    logins: tuple[Login, Login],
) -> None:
    from dw_bravo.sync import SyncQuery

    bravo = SqlServerBravo(*logins)

    first = await bravo.changes(SyncQuery("B20LME", limit=1))
    rest = await bravo.changes(SyncQuery("B20LME", after=first.rows[0].row_version))

    assert [r.data["Code"] for r in (*first.rows, *rest.rows)] == ["L1", "L2"]
    assert first.rows[0].data["LMEActual"] == "9123.50" and first.rows[0].data["Name"] == "Đồng"
    assert "Name2" not in first.rows[0].data  # the login holds no grant on it either
    assert first.rows[0].row_version < rest.rows[0].row_version
    _run(DB, "UPDATE dbo.B20LME SET LMEActual = 9200 WHERE Code = 'L1'")
    changed = await bravo.changes(SyncQuery("B20LME", after=rest.rows[-1].row_version))
    assert [r.data["Code"] for r in changed.rows] == ["L1"]
    # From the start, in rowversion order: the row changed last comes last.
    assert [r.data["Code"] for r in (await bravo.changes(SyncQuery("B20LME"))).rows] == ["L2", "L1"]


async def test_a_definition_the_read_login_cannot_see_is_could_not_check(
    logins: tuple[Login, Login],
) -> None:
    from dw_bravo_gateway.ports import BravoUnavailableError

    _run(DB, "REVOKE VIEW DEFINITION ON dbo.ufn_Prevent_Edit TO dw_test_read")
    try:
        with pytest.raises(BravoUnavailableError, match="ufn_Prevent_Edit"):
            await SqlServerBravo(*logins).fingerprint("production")
    finally:
        _run(DB, "GRANT VIEW DEFINITION ON dbo.ufn_Prevent_Edit TO dw_test_read")


async def test_the_shared_templates_guards_hold_on_a_write(logins: tuple[Login, Login]) -> None:
    """Ticket 59 with script 03c: the SO screen's template is read from
    `B00Layout` and its guards hold at the write; the branch is read from
    `B00Branch`. A document of a branch that is a group is refused."""
    bravo = _Allowed(*logins, templates={"EDIT_BizDocSO": "BizDocEditor"})
    layout = await bravo.layout("EDIT_BizDocSO")
    assert layout.missing_template is None and layout.template is not None
    command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(4))

    result = await _pipeline(bravo).execute(command, token(command))
    assert result.outcome == "written", result

    _run(DB, "UPDATE dbo.B00Branch SET IsGroup = 1 WHERE BranchCode = 'A01'")
    try:
        command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(5))
        result = await _pipeline(bravo).execute(command, token(command))
    finally:
        _run(DB, "UPDATE dbo.B00Branch SET IsGroup = 0 WHERE BranchCode = 'A01'")
    assert (result.check, result.reason) == ("rules", "blocked: CreateData")


async def test_a_template_not_found_leaves_the_plan_provisional(
    logins: tuple[Login, Login],
) -> None:
    bravo = _Allowed(*logins, templates={"EDIT_BizDocSO": "NoSuchTemplate"})
    command = SetQuantity(line=await _line(bravo, "R1"), quantity=Decimal(4))

    result = await _pipeline(bravo).execute(command, token(command))

    assert result.check == "rules" and (result.reason or "").startswith("provisional")
