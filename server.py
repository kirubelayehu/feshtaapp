
import os
import json
import hmac
import hashlib
import time
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.exc import SQLAlchemyError
from flask import request, jsonify
import secrets
# -----------------------------
# CONFIGURATION
# -----------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
FRONTEND_URL = os.environ.get(
    "FRONTEND_URL",
    "https://feshta.onrender.com"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is missing.")

# Render may provide postgres:// URLs.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True
}

db = SQLAlchemy(app)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [FRONTEND_URL]
        }
    }
)


# -----------------------------
# PLAYER DATABASE TABLE
# -----------------------------

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    telegram_id = db.Column(
        db.BigInteger,
        unique=True,
        nullable=False,
        index=True
    )

    username = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))

    coins = db.Column(
        db.Integer,
        nullable=False,
        default=1000
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )
# -----------------------------
# COIN DATABASE TABLE
# -----------------------------
class CoinTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    telegram_id = db.Column(
        db.BigInteger,
        nullable=False,
        index=True
    )

    amount = db.Column(db.Integer, nullable=False)

    transaction_type = db.Column(
        db.String(30),
        nullable=False
    )

    description = db.Column(db.String(200))

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )
# -----------------------------
# VERIFY TELEGRAM MINI APP DATA
# -----------------------------

def verify_telegram_data(init_data):

    try:
        parsed_data = dict(parse_qsl(init_data, strict_parsing=True))

        received_hash = parsed_data.pop("hash", None)

        if not received_hash:
            return None

        # Build Telegram data-check string.
        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(parsed_data.items())
        )

        # Generate Telegram secret key.
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=BOT_TOKEN.encode(),
            digestmod=hashlib.sha256
        ).digest()

        # Calculate expected hash.
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, received_hash):
            return None

        # Reject old authentication data.
        auth_date = int(parsed_data.get("auth_date", "0"))

        if auth_date > time.time() + 60:
            return None

        if time.time() - auth_date > 86400:
            return None

        user_data = json.loads(parsed_data.get("user", "{}"))

        if not user_data.get("id"):
            return None

        return user_data

    except (ValueError, TypeError, json.JSONDecodeError):
        return None


# -----------------------------
# CREATE OR FIND PLAYER
# -----------------------------

def get_or_create_player(user_data):

    telegram_id = int(user_data["id"])

    player = Player.query.filter_by(
        telegram_id=telegram_id
    ).first()

    if player is None:
        player = Player(
            telegram_id=telegram_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            coins=1000
        )

        db.session.add(player)

    else:
        player.username = user_data.get("username")
        player.first_name = user_data.get("first_name")
        player.last_name = user_data.get("last_name")

    db.session.commit()

    return player


def process_coin_transaction(telegram_id, amount, transaction_type, description):
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if transaction_type not in ("earn", "spend"):
        raise ValueError("Invalid transaction type.")

    try:
        player = Player.query.filter_by(
            telegram_id=telegram_id
        ).with_for_update().first()

        if not player:
            raise ValueError("Player not found.")

        if transaction_type == "spend":
            if player.coins < amount:
                raise ValueError("Not enough coins.")

            player.coins -= amount
        else:
            player.coins += amount

        transaction = CoinTransaction(
            telegram_id=telegram_id,
            amount=amount if transaction_type == "earn" else -amount,
            transaction_type=transaction_type,
            description=description
        )

        db.session.add(transaction)
        db.session.commit()

        return player.coins

    except Exception:
        db.session.rollback()
        raise
# -----------------------------
# HEALTH CHECK
# -----------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "FESHTA Backend"
    })


# -----------------------------
# PLAYER ACCOUNT API
# -----------------------------


@app.route("/api/me", methods=["GET"])
def get_my_account():

    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if not init_data:
        return jsonify({
            "error": "Telegram authentication required"
        }), 401

    try:
        user_data = verify_telegram_data(init_data)

        if not user_data:
            print("FESHTA ERROR: Telegram authentication failed")
            return jsonify({
                "error": "Invalid or expired Telegram authentication"
            }), 401

        player = get_or_create_player(user_data)

        return jsonify({
            "success": True,
            "player": {
                "telegram_id": player.telegram_id,
                "username": player.username,
                "first_name": player.first_name,
                "last_name": player.last_name,
                "coins": player.coins
            }
        })

    except Exception as error:
        db.session.rollback()
        app.logger.exception("FESHTA account API failed")

        return jsonify({
            "error": "Account service temporarily unavailable"
        }), 500
@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    user_data = verify_telegram_data(init_data)

    if not user_data:
        return jsonify({
            "success": False,
            "error": "Authentication failed"
        }), 401

    telegram_id = int(user_data["id"])

    transactions = (
        CoinTransaction.query
        .filter_by(telegram_id=telegram_id)
        .order_by(CoinTransaction.created_at.desc())
        .limit(50)
        .all()
    )

    return jsonify({
        "success": True,
        "transactions": [
            {
                "amount": transaction.amount,
                "type": transaction.transaction_type,
                "description": transaction.description,
                "created_at": transaction.created_at.isoformat()
            }
            for transaction in transactions
        ]
    })
@app.route("/api/lucky-spin", methods=["POST"])
def lucky_spin():
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_data = verify_telegram_data(init_data)

    if not user_data:
        return jsonify({
            "success": False,
            "error": "Authentication failed"
        }), 401

    telegram_id = int(user_data["id"])

    try:
        player = Player.query.filter_by(
            telegram_id=telegram_id
        ).with_for_update().first()

        if not player:
            return jsonify({
                "success": False,
                "error": "Player not found"
            }), 404

        spin_cost = 50

        if player.coins < spin_cost:
            return jsonify({
                "success": False,
                "error": "Not enough coins"
            }), 400

        roll = secrets.randbelow(100)

        if roll < 40:
            reward = 0
        elif roll < 70:
            reward = 25
        elif roll < 90:
            reward = 50
        elif roll < 98:
            reward = 100
        else:
            reward = 250

        player.coins -= spin_cost

        db.session.add(CoinTransaction(
            telegram_id=telegram_id,
            amount=-spin_cost,
            transaction_type="spend",
            description="Lucky Spin"
        ))

        if reward > 0:
            player.coins += reward

            db.session.add(CoinTransaction(
                telegram_id=telegram_id,
                amount=reward,
                transaction_type="earn",
                description="Lucky Spin reward"
            ))

        db.session.commit()

        return jsonify({
            "success": True,
            "reward": reward,
            "coins": player.coins
        })

    except Exception:
        db.session.rollback()
        app.logger.exception("Lucky Spin failed")

        return jsonify({
            "success": False,
            "error": "Spin failed. Please try again."
        }), 500
# -----------------------------
# CREATE DATABASE TABLES
# -----------------------------

with app.app_context():
    db.create_all()


# -----------------------------
# LOCAL DEVELOPMENT
# -----------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
