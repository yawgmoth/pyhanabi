import BaseHTTPServer
import time
import shutil
import os
import hanabi
import random

HOST_NAME = "127.0.0.1"
PORT_NUMBER = 31337

template = """

<table width="100%%">
<tr><td width="15%%" valign="top"><center><h2>Trash</h2></center><br/> 
%s
<br/>
<br/>
<b>Hints:</b> %d<br/>
<b>Mistakes:</b> %d
</td>
<td>
<center>
<h2> Other player </h2>
<table>
<tr><td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
</tr>
<tr><td colspan="5"><center><h2>Board</h2></center></td></tr>
<tr><td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
</tr>
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

def format_action((action,pnr,card)):
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
    return result
        

def show_game_state(game, player, turn):
    
    def make_ai_card((i,(col,num))):
        hintlinks = [("Hint Rank", "/%d/hintrank/%d"%(turn,i)), ("Hint Color", "/%d/hintcolor/%d"%(turn,i))]
        if game.hints == 0:
            hintlinks = []
        return make_card_image((col,num), hintlinks)
    aicards = map(make_ai_card, enumerate(game.hands[0]))
    while len(aicards) < 5:
        aicards.append("")
    def make_your_card((i,(col,num))):
        return unknown_card_image([("Play", "/%d/play/%d"%(turn,i)), ("Discard", "/%d/discard/%d"%(turn,i))])
    yourcards = []
    for i,c in enumerate(game.hands[1]):
        yourcards.append(make_your_card((i,c)))
        yourcards.append(", ".join(player.knows[i]))
    while len(yourcards) < 10:
        yourcards.append("")
    boardcards = map(make_card_image, game.board)
    trash = ["<br/>".join(map(hanabi.format_card, game.trash))]
    args = tuple(trash + [game.hints, game.hits] + aicards + boardcards + yourcards + ["<br/>".join(map(format_action, reversed(player.actions)))])
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
    

def make_card_image((col,num), links=[]):
    image = """
<svg version="1.1" width="125" height="200" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <rect width="125" height="200" x="0" y="0" fill="#66ccff"/>
    <text x="8" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    %s
    %s
    <text x="108" y="190" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
</svg>
"""
    ly = 165
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 20
    l = 35 # left
    r = 90 # right
    c = 62 # center (horizontal)
    circles = {0: [], 1: [(c,100)], 2: [(l,75),(r,125)], 3: [(l,125), (r,125), (c,75)], 4: [(l,125), (r,125), (l,75), (r,75)], 5:[(l,125), (r,125), (l,75), (r,75), (c,100)]}
    circ = "\n".join(map(lambda (x,y): make_circle(x,y,hanabi.COLORNAMES[col]), circles[num]))
    return image%(hanabi.COLORNAMES[col],str(num), circ, linktext, hanabi.COLORNAMES[col],str(num))

    
def unknown_card_image(links=[]):
    image = """
<svg version="1.1" width="125" height="200" xmlns="http://www.w3.org/2000/svg">
    <rect width="125" height="200" x="0" y="0" fill="#66ccff"/>
    %s
    <text x="25" y="145" fill="black" font-family="Arial" font-size="128">?</text>
</svg>
"""
    ly = 165
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 20
    return image%linktext
    
game = None
player = None
turn = 0

class HTTPPlayer(hanabi.Player):
    def __init__(self, name, pnr):
        self.name = name
        self.pnr = pnr
        self.actions = []
        self.knows = [set() for i in xrange(5)]
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints):
        return random.choice(valid_actions)
    def inform(self, action, player, game):
        card = None
        if action.type in [hanabi.PLAY, hanabi.DISCARD]:
            card = game.hands[player][action.cnr]
        self.actions.append((action, player,card))
        if player != self.pnr: 
            if action.type == hanabi.HINT_COLOR:
                for i, (col,num) in enumerate(game.hands[self.pnr]):
                    if col == action.col:
                        self.knows[i].add(hanabi.COLORNAMES[col])
            elif action.type == hanabi.HINT_NUMBER:
                for i, (col,num) in enumerate(game.hands[self.pnr]):
                    if num == action.num:
                        self.knows[i].add(str(num))
                
        if player == self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.knows[action.cnr]
            self.knows.append(set())
        


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
            ais = {"random": hanabi.Player, "inner": hanabi.InnerStatePlayer, "outer": hanabi.OuterStatePlayer, "self": hanabi.SelfRecognitionPlayer}
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            
            game = hanabi.Game([ai,player], hanabi.NullStream())
            game.single_turn()
            
        
        if game is None:
            s.wfile.write("<html><head><title>Hanabi</title></head>\n")
            s.wfile.write('<body><h1>Welcome to Hanabi</h1> <p>To start, choose an AI:</p>\n')
            s.wfile.write('<ul><li><a href="/new/random">Random</a></li>\n')
            s.wfile.write('<li><a href="/new/inner">Inner State</a></li>\n')
            s.wfile.write('<li><a href="/new/outer">Outer State</a></li>\n')
            s.wfile.write('<li><a href="/new/self">Self Recognition</a></li>\n')
            
            return
        
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
                game.external_turn(action)
                game.single_turn()
            
                
                
        
        s.wfile.write("<html><head><title>Hanabi</title></head>")
        s.wfile.write('<body>')
        
        s.wfile.write(show_game_state(game, player, turn))
       
        #s.wfile.write("<p>You accessed path: %s</p>" % s.path)
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