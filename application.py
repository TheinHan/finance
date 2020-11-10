import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("https://git.heroku.com/finance-th.git")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session.get("user_id")

    # get user transactions data from db
    data = db.execute("SELECT symbol, share_name, SUM(share_qty) share_qty, share_price, total FROM transactions WHERE user_id=:user_id GROUP BY symbol", user_id=user_id)

    # Grand total
    GT = 0
    rows = []

    # exclude 0 share_qty in the list
    for j in range(len(data)):
        qty = data[j]["share_qty"]
        if qty != 0:
            rows.append(data[j])

    for i in range(len(rows)):
        # to check cloud for latest price through API
        quote = lookup(rows[i]["symbol"])
        x = quote["price"]
        y = rows[i]["share_qty"]
        z = x * y
        GT += z                             # calculate grand total
        rows[i]["share_price"] = usd(x)     # GET share price
        rows[i]["total"] = usd(z)           # GET total


    bal = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=user_id)[0]["cash"]
    grandT = usd(GT + bal)                  # GET Grand Total
    balance = usd(bal)                      # GET balance

    return render_template("index.html", rows=rows, balance=balance, grandT=grandT)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # GET user id
    user_id = session.get("user_id")

    # GET user balance
    balance = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=user_id)[0]["cash"]

    if request.method == "POST":

        # GET symbol that user buy
        symbol = request.form.get("symbol").upper()

        # make sure that symbol is not blank
        if not symbol:
            return apology("missing symbol", 400)

        # make sure that share qty is not blank
        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        # make sure that share qty is valid
        elif not request.form.get("shares").isdigit():
            return apology("invalid share amount", 400)

        else:
            quote = lookup(symbol)

            # make sure that symbol is valid
            if not quote:
                return apology("invalid shares", 400)

            else:
                share_name = quote["name"]              # GET company name
                share_price = quote["price"]            # GET price of share
                share_qty = request.form.get("shares")  # GET share_qty

                # check if enough balance to buy
                buy_amt = share_price * float(share_qty)
                newbal = balance - buy_amt

                if newbal < 0:
                    return apology("insufficient fund", 400)

                else:
                    total = round(buy_amt, 2)           # GET total buy amount
                    balance = round(newbal, 2)          # GET new balance
                    dt = datetime.now()                 # GET datetime
                    now = dt.strftime("%Y-%m-%d %H:%M:%S")

                    # update transactions table
                    db.execute("""
                    INSERT INTO transactions
                    (symbol, share_name, share_qty, share_price, tx_type, tx_time, user_id, total)
                    VALUES (:symbol, :share_name, :share_qty, :share_price, :tx_type, :tx_time, :user_id, :total)
                    """, symbol=symbol, share_name=share_name, share_qty=share_qty, share_price=share_price, tx_type="BUY", tx_time=now, user_id=user_id, total=total)

                    # update balance in users table
                    db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=balance, id=user_id)

                    # route to bought alert
                    flash("Bought!")
                    return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # get user id
    user_id = session.get("user_id")

    # get transaction history from transactions table
    rows = db.execute("SELECT symbol, share_qty, share_price, tx_time FROM transactions WHERE user_id=:user_id", user_id=user_id)

    # make $ symbol
    for i in range(len(rows)):
        rows[i]["share_price"] = usd(rows[i]["share_price"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # when post request, execute get quote
    if request.method == "POST":

        symbol = request.form.get("symbol").upper()     # GET symbol
        quote = lookup(symbol)                          # take quote

        if not quote:
            return apology("invalid symbol", 400)       # make sure valid quote
        else:
            share_name = quote["name"]                  # GET company name
            price = quote["price"]
            share_price = usd(price)                    # GET share price, in USD

            # return quote with quoted template
            return render_template("quoted.html", share_name=share_name, symbol=symbol, share_price=share_price)

    # render quote template when route to quote
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        cfpassword = request.form.get("confirm_password")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 403)

        # Ensure confirm password is the same as password
        elif not cfpassword or password != cfpassword:
            return apology("Confirm_password is not the same as password", 403)

        else:
            # Ensure username is unique and not used before
            rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
            if len(rows) >= 1:
                return apology("username already exist", 400)

            # create user in the users table
            else:
                db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                username=username, hash=generate_password_hash(password))
                return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # get user id
    user_id = session.get("user_id")

    # get symbol and share quantity data from database
    data = db.execute("SELECT symbol, SUM(share_qty) share_qty FROM transactions WHERE user_id=:user_id GROUP BY symbol", user_id=user_id)
    rows = []

    for i in range(len(data)):
        j = data[i]["share_qty"]
        if j != 0:
            rows.append(data[i])

    # when received post method request
    if request.method == "POST":
        symbol = request.form.get("symbol")             # GET symbol
        sell_share_qty = request.form.get("share_qty")  # GET sell quantity

        # check if no value is selected and posted
        if not symbol:
            return apology("must choose share", 400)

        # check if sell quantity is not typed in or valid
        elif not sell_share_qty or not sell_share_qty.isdigit():
            return apology("must type share quantity", 400)

        # GET stock quantity from database
        else:
            qty = db.execute("SELECT SUM(share_qty) share_qty FROM transactions WHERE user_id=:user_id AND symbol=:symbol GROUP BY symbol",
                                    user_id=user_id, symbol=symbol)

            share_qty = qty[0]["share_qty"]             # GET available stock quantity

            # check if enough stock to sell
            if int(sell_share_qty) > share_qty:
                return apology("insufficient stock", 400)

            else:
                quote = lookup(symbol)
                share_name = quote["name"]              # GET share name
                share_price = quote["price"]            # GET share price

                x = int(sell_share_qty)
                y = x * share_price                     # calculate total amount
                total = round(y, 2)                     # GET total amount
                z = -x                                  # to update share_qty into database

                dt = datetime.now()                     # GET tx_time
                tx_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                # update transactions table in database
                db.execute("""
                INSERT INTO transactions (symbol, share_name, share_qty, share_price, tx_type, tx_time, user_id, total)
                VALUES (:symbol, :share_name, :share_qty, :share_price, :tx_type, :tx_time, :user_id, :total)
                """,
                symbol=symbol, share_name=share_name, share_qty=z, share_price=share_price, tx_type="SELL", tx_time=tx_time, user_id=user_id, total=total)

                # get cash data from users
                cash = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)

                bal = cash[0]["cash"]
                balance = bal + total                  # GET new balance

                # update new cash status
                db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=balance, user_id=user_id)

                flash("Sold!")
                return redirect("/")

    else:
        return render_template("sell.html", rows=rows)


@app.route("/dirsell", methods=["GET", "POST"])
@login_required
def dirsell():

    # GET user id
    user_id = session.get("user_id")

    # get when request method is post
    if request.method == "POST":

        symbol = request.form.get("symbol")         # GET symbol
        quote = lookup(symbol)                      # get quote
        share_price = quote["price"]                # GET price

        # GET data
        rows = db.execute("SELECT SUM(share_qty) share_qty, share_name FROM transactions WHERE symbol=:symbol AND user_id=:user_id GROUP BY symbol",
                            symbol=symbol, user_id=user_id)

        if len(rows) != 1:
            return apology("Server Error", 500)
        else:
            share_qty = rows[0]["share_qty"]        # GET share_qty
            share_name = rows[0]["share_name"]      # GET share_name

        return render_template("dirsell.html", symbol=symbol, share_qty=share_qty, share_name=share_name, share_price=share_price)

    else:
        return redirect("/")


@app.route("/confsell", methods=["GET", "POST"])
@login_required
def confsell():

    # GET user id
    user_id = session.get("user_id")

    # get when request method is post
    if request.method == "POST":

        symbol = request.form.get("symbol")         # GET symbol
        if symbol == "cancel":
            return redirect("/")

        else:
            quote = lookup(symbol)
            share_price = quote["price"]            # GET share_price

            # GET data
            rows = db.execute("SELECT SUM(share_qty) share_qty, share_name FROM transactions WHERE symbol=:symbol AND user_id=:user_id GROUP BY symbol",
                                symbol=symbol, user_id=user_id)

            if len(rows) != 1:
                return apology("Server Error", 500)
            else:
                z = rows[0]["share_qty"]
                share_qty = -z                      # GET share_qty
                share_name = rows[0]["share_name"]  # GET share_name
                total = share_price * z             # GET total

                dt = datetime.now()                 # GET tx_time
                tx_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                # update transactions table in database
                db.execute("""
                INSERT INTO transactions (symbol, share_name, share_qty, share_price, tx_type, tx_time, user_id, total)
                VALUES (:symbol, :share_name, :share_qty, :share_price, :tx_type, :tx_time, :user_id, :total)
                """,
                symbol=symbol, share_name=share_name, share_qty=share_qty, share_price=share_price, tx_type="SELL", tx_time=tx_time, user_id=user_id, total=total)

                # get cash data from users
                cash = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=user_id)

                bal = cash[0]["cash"]
                balance = bal + total                  # GET new balance

                # update new cash status
                db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=balance, user_id=user_id)

                flash("Sold!")
                return redirect("/")

    else:
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
