from db import db, chats, messages, ping
print("db:", db.name, "ping:", ping())
print("chats idx:", list(chats.list_indexes()))
print("messages idx:", list(messages.list_indexes()))
