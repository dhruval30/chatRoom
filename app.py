from flask import Flask, request, jsonify, render_template
from flask_pymongo import PyMongo
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import string
from flask_cors import CORS
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

socketio = SocketIO(app, cors_allowed_origins="*")

def generate_key(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    room_key = generate_key()
    user_name = data.get('user_name', 'Anonymous')
    mongo.db.chat_rooms.insert_one({
        'room_key': room_key,
        'messages': [],
        'participants': [user_name]
    })
    return jsonify({'room_key': room_key}), 201

@app.route('/join_room', methods=['POST'])
def join_room_route():
    data = request.json
    room_key = data.get('room_key')
    user_name = data.get('user_name', 'Anonymous')
    room = mongo.db.chat_rooms.find_one({'room_key': room_key})
    if room:
        mongo.db.chat_rooms.update_one(
            {'room_key': room_key},
            {'$addToSet': {'participants': user_name}}
        )
        return jsonify({'room_key': room_key}), 200
    else:
        return jsonify({'message': 'Room not found!'}), 404

@socketio.on('join')
def on_join(data):
    room = data['room']
    user_name = data.get('user_name', 'Anonymous')
    join_room(room)
    room_data = mongo.db.chat_rooms.find_one({'room_key': room})
    participant_count = len(room_data['participants'])
    emit('receive_message', {'user_name': 'System', 'message': f'{user_name} has joined the room.'}, room=room)
    emit('update_participant_count', {'count': participant_count}, room=room)

@socketio.on('leave')
def on_leave(data):
    room = data['room']
    user_name = data.get('user_name', 'Anonymous')
    leave_room(room)
    mongo.db.chat_rooms.update_one(
        {'room_key': room},
        {'$pull': {'participants': user_name}}
    )
    room_data = mongo.db.chat_rooms.find_one({'room_key': room})
    participant_count = len(room_data['participants'])
    emit('receive_message', {'user_name': 'System', 'message': f'{user_name} has left the room.'}, room=room)
    emit('update_participant_count', {'count': participant_count}, room=room)

@socketio.on('send_message')
def handle_send_message(data):
    room_key = data['room_key']
    message = data['message']
    user_name = data.get('user_name', 'Anonymous')
    room = mongo.db.chat_rooms.find_one({'room_key': room_key})
    if room:
        mongo.db.chat_rooms.update_one(
            {'room_key': room_key},
            {'$push': {'messages': {'user_name': user_name, 'message': message}}}
        )
        emit('receive_message', {'user_name': user_name, 'message': message}, room=room_key)
    else:
        emit('error', {'message': 'Room not found!'}, room=room_key)

@app.route('/get_messages', methods=['POST'])
def get_messages():
    data = request.json
    room_key = data.get('room_key')
    room = mongo.db.chat_rooms.find_one({'room_key': room_key})
    if room:
        return jsonify({'messages': room['messages']}), 200
    else:
        return jsonify({'message': 'Room not found!'}), 404

@app.route('/chatroom/<room_key>')
def chatroom(room_key):
    return render_template('chatroom.html', room_key=room_key)

@socketio.on('disconnect')
def on_disconnect():
    for room in socketio.rooms(request.sid):
        if room != request.sid:
            on_leave({'room': room, 'user_name': 'A user'})  

if __name__ == '__main__':
    socketio.run(app, debug=True)
