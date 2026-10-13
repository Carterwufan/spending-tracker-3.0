import math
from datetime import date
from pathlib import Path

EXPENSES_FILE = Path(__file__).with_name("expenses.txt")


def welcome():
    print("Personal Expense Tracker")
    print("------------------------")
    print("1. Add Expenses")
    print("2. View Expenses")
    print("3. View Total Expenses")
    print("4. View Monthly Expenses")
    print("5. Compare Months")
    print("6. Remove Expenses")
    print("7. Exit")
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

                parts = line.split(":", maxsplit=2)
                if len(parts) not in (2, 3) or not parts[0].strip():
                    print(
                        f"Skipping invalid expense on line {line_number}: "
                        "expected CATEGORY:AMOUNT[:YYYY-MM-DD]."
                    )
                    continue

                category, amount = parts[:2]
                try:
                    spent_on = (
                        date.today()
                        if len(parts) == 2
                        else date.fromisoformat(parts[2])
                    )
                    if len(parts) == 3 and spent_on.isoformat() != parts[2]:
                        raise ValueError
                    value = float(amount)
                    if not math.isfinite(value):
                        raise ValueError
                except ValueError:
                    print(
                        f"Skipping invalid expense on line {line_number}: "
                        "amount must be a number and date must use YYYY-MM-DD."
                    )
                    continue

                expenses.append({
                    "category": category.strip(),
                    "amount": value,
                    "date": spent_on,
                })

    except FileNotFoundError:
        print("No expenses file found; starting with an empty list.")
    return expenses


def monthly_expenses(expenses):
    totals_by_month = {}
    for expense in expenses:
        month = expense["date"].strftime("%Y-%m")
        category = expense["category"]
        totals_by_month.setdefault(month, {})
        totals_by_month[month][category] = (
            totals_by_month[month].get(category, 0) + expense["amount"]
        )

    print("\nMonthly Expenses by Category:")
    if not totals_by_month:
        print("No expenses to show.")
        print()
        return

    for month in sorted(totals_by_month):
        print(f"\n{month}:")
        month_total = 0
        for category, total in sorted(totals_by_month[month].items()):
            print(f"  {category}: ${total:.2f}")
            month_total += total
        print(f"  Total: ${month_total:.2f}")
    print()


def compare_months(expenses):
    month_text = input(
        "Enter the month to compare (YYYY-MM, blank for the current month): "
    ).strip()
    if not month_text:
        month_text = date.today().strftime("%Y-%m")

    try:
        year_text, month_number_text = month_text.split("-", maxsplit=1)
        month_start = date(int(year_text), int(month_number_text), 1)
        if (
            month_start.strftime("%Y-%m") != month_text
            or month_start == date.min
            or (month_start.year == date.max.year and month_start.month == 12)
        ):
            raise ValueError
    except ValueError:
        print("Invalid month. Enter a month in YYYY-MM format.\n")
        return

    if month_start.month == 1:
        previous_month = date(month_start.year - 1, 12, 1)
    else:
        previous_month = date(month_start.year, month_start.month - 1, 1)

    current_total = sum(
        expense["amount"]
        for expense in expenses
        if expense["date"].strftime("%Y-%m") == month_text
    )
    previous_month_text = previous_month.strftime("%Y-%m")
    previous_total = sum(
        expense["amount"]
        for expense in expenses
        if expense["date"].strftime("%Y-%m") == previous_month_text
    )
    difference = current_total - previous_total

    print(f"\nExpense Comparison: {previous_month_text} vs. {month_text}")
    print(f"{previous_month_text}: ${previous_total:.2f}")
    print(f"{month_text}: ${current_total:.2f}")
    if difference > 0:
        print(f"Spending increased by ${difference:.2f}.")
    elif difference < 0:
        print(f"Spending decreased by ${abs(difference):.2f}.")
    else:
        print("Spending was unchanged.")
    print()


def save_expenses(expenses):
    with EXPENSES_FILE.open("w") as f:
        for e in expenses:
            f.write(
                f'{e["category"]}:{e["amount"]}:{e["date"].isoformat()}\n'
            )


def add_expense(expenses):
    try:
        category = input("Enter expense category: ").strip()
        if not category or ":" in category:
            print("Enter a non-empty category without a colon.")
            return

        amount = float(input("Enter expense amount: "))
        if not math.isfinite(amount) or amount < 0.01:
            print("Enter an amount of at least 0.01.")
            return

        spent_on_text = input(
            "Enter expense date (YYYY-MM-DD, blank for today): "
        ).strip()
        spent_on = (
            date.today()
            if not spent_on_text
            else date.fromisoformat(spent_on_text)
        )
        if spent_on_text and spent_on.isoformat() != spent_on_text:
            print("Enter a date in YYYY-MM-DD format.")
            return

        expense = {"category": category, "amount": amount, "date": spent_on}
        expenses.append(expense)
        try:
            save_expenses(expenses)
        except OSError as error:
            expenses.pop()
            print(f"Could not save the expense: {error}")
            return
        print("Expense added successfully!")

    except ValueError:
        print("Invalid amount or date. Please check your entry.")


def view_expenses(expenses):
    if not expenses:
        print("\nNo expenses to show.")
        return

    print("\nExpenses:")
    for i, e in enumerate(expenses, start=1):
        print(f'{i}. {e["category"]} = ${e["amount"]:.2f} ({e["date"]})')
    print()


def view_total_expenses(expenses):
    total = sum(expense["amount"] for expense in expenses)
    print(f"\nTotal Expenses: ${total:.2f}")


def remove_expense(expenses):
    if not expenses:
        print("\nNo expenses to remove.")
        return

    view_expenses(expenses)
    try:
        number = int(input("Enter the number of the expense to remove: "))
        if 1 <= number <= len(expenses):
            removed = expenses.pop(number - 1)
            save_expenses(expenses)
            print(f'Removed: {removed["category"]} - ${removed["amount"]:.2f}')
        else:
            print("Invalid number.\n")
    except ValueError:
        print("Enter a valid number.\n")


def main():
    welcome()
    expenses = load_expenses()
    while True:
        choice = input("Choose: ")
        if choice == "1":
            add_expense(expenses)
        elif choice == "2":
            view_expenses(expenses)
        elif choice == "3":
            view_total_expenses(expenses)
        elif choice == "4":
            monthly_expenses(expenses)
        elif choice == "5":
            compare_months(expenses)
        elif choice == "6":
            remove_expense(expenses)
        elif choice == "7":
            print("Exiting the program. Goodbye!")
            return
        else:
            print("Invalid Input")


if __name__ == "__main__":
    main()
