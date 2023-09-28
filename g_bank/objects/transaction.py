from mongoengine import *

class db_BankTransaction(Document):
    account = StringField(required=True)
    amount = IntField(required=True)
    timestamp = IntField(required=True)
    user = IntField(required=True)
    comment = StringField(default="")