import BaseHTTPServer
import time
import shutil
import os
import hanabi
import random

HOST_NAME = "127.0.0.1"
PORT_NUMBER = 31337

HAND = 0
TRASH = 1
BOARD = 2

template = """

<table width="100%%">
<tr><td width="15%%" valign="top"><center><h2>Trash</h2></center><br/> 
%s
<br/>
<br/>
<b>Hints:</b> %d<br/>
<b>Mistakes:</b> %d<br/>
<b>Cards left:</b> %d<br/>
</td>
<td>
<center>
<h2> Other player </h2>
<table>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
%s
<tr><td colspan="5"><center><h2>You</h2></center></td></tr>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
</table>
</center>
</td>
<td width="15%%" valign="top"><center> <h2>Actions</h2> </center><br/>%s</td>
</tr>
</table>
"""

board_template = """<tr><td colspan="5"><center>%s</center></td></tr>
<tr><td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
</tr>"""

def format_board(game, show):
    if not game.started:
        return '<tr><td colspan="5"><center><h1><a href="/start/">Start Game</a></h1></center></td></tr>'
    title = "<h2>Board</h2>"
    if game.done():
        title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/restart/">New game</a>'
    def make_board_image((i,card)):
        return make_card_image(card, [], (BOARD,0,i) in show)
    boardcards = map(make_board_image, enumerate(game.board))
    args = tuple([title] + boardcards)
    return board_template%args

def format_action((i,(action,pnr,card))):
    result = "You "
    other = "the AI"
    otherp = "their"
    if pnr == 0:
        result = "AI "
        other = "you"
        otherp = "your"
    if action.type == hanabi.PLAY:
        result += " played " + hanabi.format_card(card)
    elif action.type == hanabi.DISCARD:
        result += " discard " + hanabi.format_card(card)
    else:
        result += " hinted %s about all %s "%(other, otherp)
        if action.type == hanabi.HINT_COLOR:
            result += hanabi.COLORNAMES[action.col] + " cards"
        else:
            result += str(action.num) + "s"
    if i == 0:
        return "<b>" + result + '</b> <a href="/explain" target="_blank">(Explain)</a><br/>'
    return result

def show_game_state(game, player, turn):
    
    def make_ai_card((i,(col,num)), highlight):
        hintlinks = [("Hint Rank", "/%d/hintrank/%d"%(turn,i)), ("Hint Color", "/%d/hintcolor/%d"%(turn,i))]
        if game.hints == 0 or game.done() or not game.started:
            hintlinks = []
            highlight = False
        return make_card_image((col,num), hintlinks, highlight)
    aicards = []
    for i,c in enumerate(game.hands[0]):
        aicards.append(make_ai_card((i,c), (HAND, 0, i) in player.show))
        aicards.append(", ".join(player.aiknows[i]))
    
    while len(aicards) < 10:
        aicards.append("")
    def make_your_card((i,(col,num)), highlight):
        playlinks = [("Play", "/%d/play/%d"%(turn,i)), ("Discard", "/%d/discard/%d"%(turn,i))]
        if game.done() or not game.started:
            playlinks = []
        return unknown_card_image(playlinks, highlight)
    yourcards = []
    for i,c in enumerate(game.hands[1]):
        if game.done():
            yourcards.append(make_ai_card((i,c), False))
        else:
            yourcards.append(make_your_card((i,c), (HAND, 1, i) in player.show))
        yourcards.append(", ".join(player.knows[i]))
    while len(yourcards) < 10:
        yourcards.append("")
    board = format_board(game, player.show)
    foundtrash = [False]
    def format_trash(c):
        result = hanabi.format_card(c)
        if (TRASH, 0, -1) in player.show and c == game.trash[-1] and not foundtrash[0]:
            foundtrash[0] = True
            return '<font color="red">'+ result + "</font>"
        return result
    localtrash = game.trash[:]
    localtrash.sort()
    trash = ["<br/>".join(map(format_trash, localtrash))]
    args = tuple(trash + [game.hints, 3-game.hits, len(game.deck)] + aicards + [board] + yourcards + ["<br/>".join(map(format_action, enumerate(list(reversed(player.actions))[:25])))])
    return template%args


def make_circle(x, y, col):
    x += random.randint(-5,5)
    y += random.randint(-5,5)
    r0 = random.randint(0,180)
    r1 = r0 + 360
    result = """
    <circle cx="%f" cy="%d" r="10" stroke="%s" stroke-width="4" fill="none">
       <animate attributeName="r" from="1" to="25" dur="2s" repeatCount="indefinite"/>
       <animate attributeName="stroke-dasharray" values="32, 32; 16, 16; 8,8; 4,4; 2,6; 1,7;" dur="2s" repeatCount="indefinite" calcMode="discrete"/>
       <animateTransform attributeName="transform" attributeType="XML" type="rotate" from="%f %f %f" to="%f %f %f" dur="2s" begin="0s" repeatCount="indefinite"/>
    </circle>
    """
    return result%(x,y,col, r0, x,y, r1, x,y)
    

def make_card_image((col,num), links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="200" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <rect width="125" height="200" x="0" y="0" fill="#66ccff"%s/>
    <text x="8" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    <text x="50" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    %s
    %s
    <text x="108" y="190" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
</svg>
"""
    ly = 155
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 25
    l = 35 # left
    r = 90 # right
    c = 62 # center (horizontal)
    circles = {0: [], 1: [(c,100)], 2: [(l,75),(r,125)], 3: [(l,125), (r,125), (c,75)], 4: [(l,125), (r,125), (l,75), (r,75)], 5:[(l,125), (r,125), (l,75), (r,75), (c,100)]}
    circ = "\n".join(map(lambda (x,y): make_circle(x,y,hanabi.COLORNAMES[col]), circles[num]))
    highlighttext = ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext, hanabi.COLORNAMES[col],str(num), hanabi.COLORNAMES[col], hanabi.COLORNAMES[col], circ, linktext, hanabi.COLORNAMES[col],str(num))

    
def unknown_card_image(links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="200" xmlns="http://www.w3.org/2000/svg">
    <rect width="125" height="200" x="0" y="0" fill="#66ccff"%s/>
    %s
    <text x="25" y="145" fill="black" font-family="Arial" font-size="128">?</text>
</svg>
"""
    ly = 155
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 25
    highlighttext= ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext,linktext)
    
game = None
player = None
turn = 0



class HTTPPlayer(hanabi.Player):
    def __init__(self, name, pnr):
        self.name = name
        self.pnr = pnr
        self.actions = []
        self.knows = [set() for i in xrange(5)]
        self.aiknows = [set() for i in xrange(5)]
        self.show = []
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints):
        return random.choice(valid_actions)
    def inform(self, action, player, game):
        if player == 1:
            self.show = []
        card = None
        if action.type in [hanabi.PLAY, hanabi.DISCARD]:
            card = game.hands[player][action.cnr]
        self.actions.append((action, player,card))
        if player != self.pnr: 
            if action.type == hanabi.HINT_COLOR:
                for i, (col,num) in enumerate(game.hands[self.pnr]):
                    if col == action.col:
                        self.knows[i].add(hanabi.COLORNAMES[col])
                        self.show.append((HAND,self.pnr,i))
            elif action.type == hanabi.HINT_NUMBER:
                for i, (col,num) in enumerate(game.hands[self.pnr]):
                    if num == action.num:
                        self.knows[i].add(str(num))
                        self.show.append((HAND,self.pnr,i))
        else:
            if action.type == hanabi.HINT_COLOR:
                for i, (col,num) in enumerate(game.hands[action.pnr]):
                    if col == action.col:
                        self.aiknows[i].add(hanabi.COLORNAMES[col])
                        self.show.append((HAND,action.pnr,i))
            elif action.type == hanabi.HINT_NUMBER:
                for i, (col,num) in enumerate(game.hands[action.pnr]):
                    if num == action.num:
                        self.aiknows[i].add(str(num))
                        self.show.append((HAND,action.pnr,i))
 
        if action.type in [hanabi.PLAY, hanabi.DISCARD] and player == 0:
            newshow = []
            for (where,who,what) in self.show:
                if who == 0 and where == HAND:
                    if what < action.cnr:
                        newshow.append((where,who,what))
                    elif what > action.cnr:
                        newshow.append((where,who,what-1))
                else:
                    newshow.append((where,who,what))
            self.show = newshow
        if action.type == hanabi.DISCARD:
            self.show.append((TRASH,0,-1))
        elif action.type == hanabi.PLAY:
            (col,num) = game.hands[player][action.cnr]
            if game.board[col][1] + 1 == num:
                self.show.append((BOARD,0,col))
            else:
                self.show.append((TRASH,0,-1))
        if player == self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.knows[action.cnr]
            self.knows.append(set())
        if player != self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.aiknows[action.cnr]
            self.aiknows.append(set())
        


class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_HEAD(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
    def do_GET(s):
        """Respond to a GET request."""
        if s.path.startswith("/img/"):
            s.send_response(404)
            s.send_header("Content-type", "image/svg")
            return
            # if we wanted to host the actual images, this is where that would happen
            if "/" not in s.path[5:] and "\\" not in s.path[5:]:
                fname = s.path[1:]
                fs = os.stat(fname)
                s.send_header("Content-Length", fs[6])
                s.end_headers()
                f = open(fname, "rb")
                shutil.copyfileob(f, s.wfile)
                f.close()
            return
        global game, player, turn
        
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
        
        
            
        
        if s.path.startswith("/new/"):
            type = s.path[5:]
            ais = {"random": hanabi.Player, "inner": hanabi.InnerStatePlayer, "outer": hanabi.OuterStatePlayer, "self": hanabi.SelfRecognitionPlayer, "intentional": hanabi.IntentionalPlayer}
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            
            game = hanabi.Game([ai,player], hanabi.NullStream())
            game.started = False
            
        
            
        
        if game is None or s.path.startswith("/restart/"):
            s.wfile.write("<html><head><title>Hanabi</title></head>\n")
            s.wfile.write('<body><h1>Welcome to Hanabi</h1> <p>To start, choose an AI:</p>\n')
            s.wfile.write('<ul><li><a href="/new/random">Random</a></li>\n')
            s.wfile.write('<li><a href="/new/inner">Inner State</a></li>\n')
            s.wfile.write('<li><a href="/new/outer">Outer State</a></li>\n')
            s.wfile.write('<li><a href="/new/self">Self Recognition</a></li>\n')
            s.wfile.write('<li><a href="/new/intentional">Intentional Player</a></li>\n')
            
            return
            
        if s.path.startswith("/explain"):
            s.show_explanation()
            return 
            
        if s.path.startswith("/start/"):
            game.single_turn()
            game.started = True
            
        
        parts = s.path.strip("/").split("/")
        if parts[0] == str(turn):
            actionname = parts[1]
            index = int(parts[2])
            action = None
            if actionname == "hintcolor" and game.hints > 0:
                col = game.hands[0][index][0]
                action = hanabi.Action(hanabi.HINT_COLOR, pnr=0, col=col)
            elif actionname == "hintrank" and game.hints > 0:
                nr = game.hands[0][index][1]
                action = hanabi.Action(hanabi.HINT_NUMBER, pnr=0, num=nr)
            elif actionname == "play":
                action = hanabi.Action(hanabi.PLAY, pnr=1, cnr=index)
            elif actionname == "discard":
                action = hanabi.Action(hanabi.DISCARD, pnr=1, cnr=index)
            
            if action:
                turn += 1
                print "performing", action
                game.external_turn(action)
                game.single_turn()
            
                
                
        
        s.wfile.write("<html><head><title>Hanabi</title></head>")
        s.wfile.write('<body>')
        
        s.wfile.write(show_game_state(game, player, turn))
       
        s.wfile.write("</body></html>")
        
    def show_explanation(s):
        s.wfile.write("<html><head><title>Hanabi - AI Explanation</title></head>")
        s.wfile.write('<body>')
        
        s.wfile.write('<table border="1">')
        s.wfile.write('<tr><th>Description</th><th>Card 1</th><th>Card 2</th><th>Card 3</th><th>Card 4</th><th>Card 5</th>\n')
        for line in game.players[0].explanation:
            s.wfile.write('<tr>\n')
            for item in line:
                s.wfile.write('\t<td>%s</td>\n'%(str(item).replace("\n", "<br/>")))
            s.wfile.write('</tr>\n')
        s.wfile.write("</table>\n")
       
        
        s.wfile.write("</body></html>")
 
if __name__ == '__main__':
    server_class = BaseHTTPServer.HTTPServer
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    print time.asctime(), "Server Starts - %s:%s" % (HOST_NAME, PORT_NUMBER)
    try:
       httpd.serve_forever()
    except KeyboardInterrupt:
     pass
    httpd.server_close()
    print time.asctime(), "Server Stops - %s:%s" % (HOST_NAME, PORT_NUMBER)