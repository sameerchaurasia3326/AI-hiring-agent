import secrets
import string
import hashlib
import bcrypt

# Global security settings
OTP_EXPIRY_MINUTES = 10

def generate_otp(length: int = 6) -> str:
    """Generate a secure numeric OTP."""
    digits = string.digits
    return ''.join(secrets.choice(digits) for _ in range(length))

def hash_otp(otp: str) -> str:
    """Hash the OTP using bcrypt (direct) to avoid passlib bugs."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(otp.encode('utf-8'), salt).decode('utf-8')

def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify a plain OTP against its hash."""
    return bcrypt.checkpw(plain_otp.encode('utf-8'), hashed_otp.encode('utf-8'))

def hash_password(password: str) -> str:
    """Hash the password using bcrypt (direct)."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
