## Bot commands:

- !clear
- !create-comp [Comp message ID] [Comp channel ID]
- !register [Albion nickname]
- !bal
- !bal-add [Albion nickname] [Amount]
- !bal-remove [Albion nickname] [Amount]

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

## Balances:

- In order to check your balance, use the **!bal** command. It will find first mention of your **Discord ID** in associated spreadsheet and return value stored in the **Silver** column.
*Example:*  
```
!bal
```

- In order to add balance to the user, use **!bal-add [Albion nickname] [Amount]** command. It takes 2 parameters: **Albion nickname** and **Amount**. It will find first mention of **Albion nickname** in associated spreadsheet, read value stored in the **Silver** column, and update **Silver** column by adding **Amount** to current **Silver** value.
*Example:*  
```
!bal-add Otaman 1000000
```

- In order to remove balance from the user, use **!bal-remove [Albion nickname] [Amount]** command. It takes 2 parameters: **Albion nickname** and **Amount**. It will find first mention of **Albion nickname** in associated spreadsheet, read value stored in the **Silver** column, and update **Silver** column by deducting **Amount** from current **Silver** value.
*Example:*  
```
!bal-remove Otaman 1000000
```

*Notes:*  
- Balances cannot be lower than 0  
- If **Amount** is not an integer value, command will not work and send a warning message
- If **Amount** is an integer value but < 0, command will not work and send a warning message

## How to set up and link Google Sheet:

- *TODO*

## How to set up Bot:

- *TODO*