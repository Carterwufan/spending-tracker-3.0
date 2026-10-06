from pathlib import Path

EXPENSES_FILE = Path(__file__).with_name("expenses.txt")

def welcome():
    print("Personal Expense Tracker")
    print("------------------------")
    print("1. Add Expenses")
    print("2. View Expenses")
    print("3. View Total Expenses")
    print("4. Remove Expenses")
    print("5. Exit")
    print("------------------------")
    print()


def load_expenses():
    expenses = []

    try:
        with EXPENSES_FILE.open("r") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(":", maxsplit=1)
                if len(parts) != 2 or not parts[0].strip():
                    print(
                        f"Skipping invalid expense on line {line_number}: "
                        "expected CATEGORY:AMOUNT."
                    )
                    continue

                category, amount = parts
                try:
                    expenses.append(
                        {"category": category.strip(), "amount": float(amount)}
                    )
                except ValueError:
                    print(
                        f"Skipping invalid expense on line {line_number}: "
                        "amount must be a number."
                    )

    except FileNotFoundError:
        print("No expenses file found; starting with an empty list.")
    return expenses

def save_expenses(expenses):
    with EXPENSES_FILE.open("w") as f:
        for e in expenses:
            f.write(f'{e["category"]}:{e["amount"]}\n')


def add_expense(expenses):
    try:
        category = input("Enter expense category: ")
        amount = float(input("Enter expense amount: "))
        expenses.append({"category": category, "amount": amount})
        save_expenses(expenses)
        print("Expense added successfully!")

    except ValueError:
        print("Invalid amount. Please enter a valid number.")

    except Exception as e:
        print(e)

def view_expenses(expenses):
    if not expenses:
            print("\n No expenses to remove.")
            return
    
    print("\nExpenses:")
    i = 1
    for e in expenses:
        print(f"{i}. {e["category"]} = {e["amount"]}$")
        i += 1
    print()

def view_total_expenses(expenses):
    total = 0
    for e in expenses:
        total += (e["amount"])

    print(f"\nTotal Expenses: {total}$")

def remove_expense(expenses):
    if not expenses:
        print("\n No expenses to remove.")
        return

    view_expenses(expenses)
    try:
        number = int(input("Enter the number of the expense to remove: "))
        if number >= 1 and number <= len(expenses):
            removed = expenses.pop(number - 1)
            save_expenses(expenses)
            print(f"Removed: {removed["category"]} - {removed["amount"]}$")
        else:
            print("Invalid Number \n")
    except ValueError:
        print("Enter a valid number \n")

def main():
    welcome()
    expenses = load_expenses()
    while True:
        choice = input("Choose): ")
        if choice == "1":
            add_expense(expenses)
        elif choice == "2":
            view_expenses(expenses)
        elif choice == "3":
            view_total_expenses(expenses)
        elif choice == "4":
            remove_expense(expenses)
        elif choice == "5":
            print("Exiting the program. Goodbye!")
            return
        else:
            print("Invalid Input")

main()

