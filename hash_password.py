import getpass

from werkzeug.security import generate_password_hash


def main():
    password = getpass.getpass("Master password: ")
    confirmation = getpass.getpass("Confirm master password: ")
    if not password:
        raise SystemExit("Password cannot be empty.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print(generate_password_hash(password, method="scrypt"))


if __name__ == "__main__":
    main()
