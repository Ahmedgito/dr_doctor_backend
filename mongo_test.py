from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")

try:
    client.admin.command("ping")
    print("MongoDB is running!")
except Exception as e:
    print("MongoDB NOT running:", e)

