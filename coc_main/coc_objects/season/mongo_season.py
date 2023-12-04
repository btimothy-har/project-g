
# d_season = {
#     '_id': string,
#     's_is_current': bool,
#     's_month': int,
#     's_year': int,
#     'clangames_max': int,
#     'cwl_signup': bool
#     }

class dSeason(Document):
    s_id = StringField(primary_key=True,required=True)
    s_is_current = BooleanField(default=False)
    s_month = IntField(default=0)
    s_year = IntField(default=0)
    clangames_max = IntField(default=4000)
    cwl_signup = BooleanField(default=False)