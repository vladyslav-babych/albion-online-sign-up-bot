async def is_admin(member):
    return any(role.permissions.administrator for role in member.roles)
