COL_DISCORD_ID = 1
COL_ALBION_NICKNAME = 3
COL_SILVER = 4


def _find_first_matched_target(worksheet, col_index: int, target: str):
    values = worksheet.col_values(col_index)
    for row_index, value in enumerate(values, start=1):
        if value == target:
            return row_index
    return None


def _read_silver(worksheet, row_index: int) -> int:
    raw_silver = worksheet.cell(row_index, COL_SILVER).value
    if raw_silver is None or raw_silver == "":
        return 0
    return int(raw_silver)


async def get_balance(context, worksheet, nickname: str = None):
    try:
        if nickname is None:
            row_index = _find_first_matched_target(worksheet, COL_DISCORD_ID, str(context.author.id))
            mention = context.author.mention
        else:
            row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
            discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
            mention = f"<@{discord_id}>"
        if row_index is None:
            await context.send("Balance not found.")
            return

        silver = _read_silver(worksheet, row_index)
        await context.send(f"{mention} balance: **{silver}** :coin:")
    except Exception as e:
        await context.send(f"Error: {e}")


async def remove_balance(context, worksheet, nickname: str, amount: int):
    try:
        row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
        if row_index is None:
            await context.send(f"Character **{nickname}** not found.")
            return

        current_silver = _read_silver(worksheet, row_index)
        updated_silver = max(current_silver - amount, 0)
        worksheet.update_cell(row_index, COL_SILVER, str(updated_silver))
        
        discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
        mention = f"<@{discord_id}>"
        await context.send(f"{mention} balance: **{updated_silver}** :coin:")

    except Exception as e:
        await context.send(f"Error: {e}")


async def add_balance(context, worksheet, nickname: str, amount: int):
    try:
        row_index = _find_first_matched_target(worksheet, COL_ALBION_NICKNAME, nickname)
        if row_index is None:
            await context.send(f"Character **{nickname}** not found.")
            return

        current_silver = _read_silver(worksheet, row_index)
        updated_silver = current_silver + amount
        worksheet.update_cell(row_index, COL_SILVER, str(updated_silver))
        
        discord_id = worksheet.cell(row_index, COL_DISCORD_ID).value
        mention = f"<@{discord_id}>"
        await context.send(f"{mention} balance: **{updated_silver}** :coin:")

    except Exception as e:
        await context.send(f"Error: {e}")