class Game:
    def __init__(self, serv_num):
        self.guesses = dict()
        self.guessed = None
        self.server  = serv_num
