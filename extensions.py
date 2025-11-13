from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_migrate import Migrate

# single shared instances
db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
# prefer a threading async mode on Windows to avoid unstable eventlet/websocket behavior
# client will fall back to polling which is more reliable on Windows dev environments
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
migrate = Migrate()
