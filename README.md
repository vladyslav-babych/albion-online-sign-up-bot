## Bot commands:

- !clear
- !create-comp [Comp message ID] [Comp channel ID]
- !register [Albion Online nickname]

## Notes:

- In order to use **!clear** command, user is required to have **Manage Messages** permission.

- In order to copy **Message ID** or **Channel ID**, user has to have **Developer Mode** turned on in discord settings.

- In order to use force sign out, user is required to have **Manage Messages** permission.

## Character registration:

**!register** command will add indicated nickname to the associated google sheet with the user **Discord ID**.  
Upon successfull registration:  
- Changes server nickname to one that was indicated during registration.  
- Adds **Fed** role to the user that will grand access to main discord channels.  
- Sets silver balance to **0**.

## Sign up logic:

- In order to sign up for a role, just put the associated role number in the thread below.  
*Example:*  
```
1
```

- In order to sign out from a role, just put the minus "-" sign in the thread below.  
*Example:*
```
-
```

- Officers can force sign out member by writing the role number with a minus sign.  
*Example:*  
```
-1
```

- Officers can force sign up members by mentioning them in the thread with a role number.  
*Example:*  
```
@User 1
```

## Parties creation:

- Each individual party should start with the **Party** word and its number or individual name.  
*Example:*  
```
Party 1
```
```
Party BM
```

- Each role in the party should be numbered and have a name.  
*Example:*  
```
Party 1
1. Tank
2. Suppord
3. DPS
4. Heal
```

- If you want to create multiple parties, each party should be divided by blank row.  
*Example:* 
```
Party 1
1. Tank
2. Suppord
3. DPS
4. Heal

Party 2
5. Tank
6. Suppord
7. DPS
8. Heal

Party BM
9. Beetle
10. Behemoth
11. Chariot
12. Venom Basilisk
```
