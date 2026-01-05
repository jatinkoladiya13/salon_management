

def fun_valid_password(value):

    if " " in value:
        return "Password should not contain any space."
   
    # password should not contain at least one digit, one uppercase, one lowercase and one special character
    if not any(char.isdigit() for char in value):
        return "Password should contain at least one digit."
    
    if not any(char.isupper() for char in value):
        return "Password should contain at least one uppercase."
    
    if not any(char.islower() for char in value):
        return "Password should contain at least one lowercase."
    
    if not any(char in '!@#$%^&*()_+}{":?><,./;' for char in value):
        raise "Password should contain at least one special character."