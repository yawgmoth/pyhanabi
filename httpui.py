import BaseHTTPServer
import time
import shutil
import os
import hanabi
import random
import hashlib
import tutorial
import sys
import traceback
import consent
from cgi import parse_header, parse_multipart
from urlparse import parse_qs
from serverconf import HOST_NAME, PORT_NUMBER


HAND = 0
TRASH = 1
BOARD = 2
TRASHP = 3

debug = False


errlog = sys.stdout
if not debug:
    errlog = file("hanabi.log", "w")



template = """

<table width="100%%">
<tr><td width="15%%" valign="top"><br/> 

<table style="font-size:14pt" width="100%%">
<tr><td>
<table width="100%%" style="font-size:14pt"> 
<tr><td width="85%%"><b>Hint tokens left:</b></td><td> %s</td></tr>
<tr><td><b>Mistakes made so far:</b></td><td> %s</td></tr>
<tr><td><b>Cards left in deck:</b></td><td> %s</td></tr>
</table></td>
</tr>
<tr><td>
<center><h2>Discarded</h2></center>
%s
</td></tr>
</table>
</div>
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
<td width="15%%" valign="top"><center> <h2>Actions</h2> </center><br/>
<div style="font-size:14pt">
%s
</div></td>
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

def format_board(game, show, gid):
    if not game.started:
        return '<tr><td colspan="5"><center><h1><a href="/gid%s/start/">Start Game</a></h1></center></td></tr>'%gid
    title = "<h2>Board</h2>"
    if game.done():
        if game.dopostsurvey:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/postsurvey/%s">Continue</a>'%gid
        elif game.study:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/new/study/%s">Play again</a>'%gid
        else:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/restart/">New game</a>'
    def make_board_image((i,card)):
        return make_card_image(card, [], (BOARD,0,i) in show)
    boardcards = map(make_board_image, enumerate(game.board))
    args = tuple([title] + boardcards)
    return board_template%args

def format_action((i,(action,pnr,card)), gid):
    result = "You "
    other = "the AI"
    otherp = "their"
    if pnr == 0:
        result = "AI "
        other = "you"
        otherp = "your"
    if i <= 1:
        result += " just "
     
    if action.type == hanabi.PLAY:
        result += " played <b>" + hanabi.format_card(card) + "</b>"
    elif action.type == hanabi.DISCARD:
        result += " discarded <b>" + hanabi.format_card(card) + "</b>"
    else:
        result += " hinted %s about all %s "%(other, otherp)
        if action.type == hanabi.HINT_COLOR:
            result += hanabi.COLORNAMES[action.col] + " cards"
        else:
            result += str(action.num) + "s"
    if i == 0:
        explainlink = ''
        if debug:
            explainlink =  '<a href="/gid%s/explain" target="_blank">(Explain)</a>'%gid
        
        return "<b>" + result + '</b>%s<br/><br/>'%explainlink
    if i == 1:
        return result + '<br/><br/>'
    return '<div style="color: gray;">' + result + '</div>'

def show_game_state(game, player, turn, gid):
    
    def make_ai_card((i,(col,num)), highlight):
        hintlinks = [("Hint Rank", "/gid%s/%d/hintrank/%d"%(gid,turn,i)), ("Hint Color", "/gid%s/%d/hintcolor/%d"%(gid,turn,i))]
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
        playlinks = [("Play", "/gid%s/%d/play/%d"%(gid,turn,i)), ("Discard", "/gid%s/%d/discard/%d"%(gid,turn,i))]
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
    board = format_board(game, player.show, gid)
    foundtrash = []
    def format_trash(c):
        result = hanabi.format_card(c)
        if (TRASH, 0, -1) in player.show and c == game.trash[-1] and not foundtrash[0]:
            foundtrash[0] = True
            return result + "<b>(just discarded)</b>"
        if (TRASHP, 0, -1) in player.show and c == game.trash[-1] and not foundtrash[0]:
            foundtrash[0] = True
            return result + "<b>(just played)</b>"
        return result
    localtrash = game.trash[:]
    localtrash.sort()
    discarded = {}
    trashhtml = '<table width="100%%" style="border-collapse: collapse"><tr>\n'
    for i,c in enumerate(hanabi.ALL_COLORS):
        style = "border-bottom: 1px solid #000"
        if i > 0:
            style += "; border-left: 1px solid #000"
        trashhtml += '<td valigh="top" align="center" style="%s" width="20%%">%s</td>\n'%(style, hanabi.COLORNAMES[c])
        discarded[c] = []
        for (col,num) in game.trash:
            if col == c:
                if (TRASH, 0, -1) in player.show and (col,num) == game.trash[-1] and (col,num) not in foundtrash:
                    foundtrash.append((col,num))
                    discarded[c].append('<div style="color: red;">%d</div>'%(num))
                elif (TRASH, 0, -2) in player.show and (col,num) == game.trash[-2] and (col,num) not in foundtrash:
                    foundtrash.append((col,num))
                    discarded[c].append('<div style="color: red;">%d</div>'%(num))
                else:
                    discarded[c].append('<div>%d</div>'%num)
        discarded[c].sort()
    trashhtml += '</tr><tr style="height: 150pt">\n'
    for i,c in enumerate(hanabi.ALL_COLORS):
        style= ' style="vertical-align:top"'
        if i > 0:
            style=  ' style="border-left: 1px solid #000; vertical-align:top"'
        trashhtml += '<td valigh="top" align="center" %s>%s</td>\n'%(style, "\n".join(discarded[c]))
    trashhtml += "</tr></table><br/>"
    if foundtrash:
        trashhtml += 'Cards written in <font color="red">red</font> have been discarded or misplayed since your last turn.'
    
    trash = [trashhtml] #["<br/>".join(map(format_trash, localtrash))]
    hints = game.hints
    if hints == 0:
        hints = '<div style="font-weight: bold; font-size: 20pt">0</div>'
    mistakes = 3-game.hits
    if mistakes == 2:
        mistakes = '<div style="font-weight: bold; font-size: 20pt; color: red">2</div>'
    cardsleft = len(game.deck)
    if cardsleft < 5:
        cardsleft = '<div style="font-weight: bold; font-size: 20pt">%d</div>'%cardsleft
    args = tuple([str(hints), str(mistakes), str(cardsleft)] + trash + aicards + [board] + yourcards + ["\n".join(map(lambda x: format_action(x,gid), enumerate(list(reversed(player.actions))[:15])))])
    return template%args


def make_circle(x, y, col):
    x += random.randint(-5,5)
    y += random.randint(-5,5)
    r0 = random.randint(0,180)
    r1 = r0 + 360
    result = """
    <circle cx="%f" cy="%d" r="10" stroke="%s" stroke-width="4" fill="none">
       <animate attributeName="r" from="1" to="22" dur="2s" repeatCount="indefinite"/>
       <animate attributeName="stroke-dasharray" values="32, 32; 16, 16; 8,8; 4,4; 2,6; 1,7;" dur="2s" repeatCount="indefinite" calcMode="discrete"/>
       <animateTransform attributeName="transform" attributeType="XML" type="rotate" from="%f %f %f" to="%f %f %f" dur="2s" begin="0s" repeatCount="indefinite"/>
    </circle>
    """
    return result%(x,y,col, r0, x,y, r1, x,y)
    

def make_card_image((col,num), links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    <text x="8" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    <text x="50" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    %s
    %s
    <text x="108" y="155" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
</svg>
"""
    ly = 130
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 23
    l = 35 # left
    r = 90 # right
    c = 62 # center (horizontal)
    
    t = 45 # top
    m = 70 # middle (vertical)
    b = 95 # bottom
    circles = {0: [], 1: [(c,m)], 2: [(l,t),(r,b)], 3: [(l,b), (r,b), (c,t)], 4: [(l,b), (r,b), (l,t), (r,t)], 5:[(l,b), (r,b), (l,t), (r,t), (c,m)]}
    circ = "\n".join(map(lambda (x,y): make_circle(x,y,hanabi.COLORNAMES[col]), circles[num]))
    highlighttext = ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext, hanabi.COLORNAMES[col],str(num), hanabi.COLORNAMES[col], hanabi.COLORNAMES[col], circ, linktext, hanabi.COLORNAMES[col],str(num))

    
def unknown_card_image(links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    %s
    <text x="35" y="90" fill="black" font-family="Arial" font-size="100">?</text>
</svg>
"""
    ly = 130
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 23
    highlighttext= ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext,linktext)
    
games = {}
participants = {}
participantstarts = {}
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
            newshow = []
            for (t,w1,w2) in self.show:
                if t == TRASH:
                    newshow.append((t,w1,w2-1))
                else:
                    newshow.append((t,w1,w2))
            self.show = newshow
            self.show.append((TRASH,0,-1))
            
        elif action.type == hanabi.PLAY:
            (col,num) = game.hands[player][action.cnr]
            if game.board[col][1] + 1 == num:
                self.show.append((BOARD,0,col))
            else:
                newshow = []
                for (t,w1,w2) in self.show:
                    if t == TRASH:
                        newshow.append((t,w1,w2-1))
                    else:
                        newshow.append((t,w1,w2))
                self.show = newshow
                self.show.append((TRASH,0,-1))
        if player == self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.knows[action.cnr]
            self.knows.append(set())
        if player != self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.aiknows[action.cnr]
            self.aiknows.append(set())
        

ais = {"random": hanabi.Player, "inner": hanabi.InnerStatePlayer, "outer": hanabi.OuterStatePlayer, "self": hanabi.SelfRecognitionPlayer, "intentional": hanabi.IntentionalPlayer, "full": hanabi.SelfIntentionalPlayer}

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_HEAD(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
    def do_GET(s):
        try:
            return s.perform_response()
        except Exception:
            errlog.write(traceback.format_exc())
            errlog.flush()
            
    def invalid(s, gid):
        if len(gid) != 16:
            return True
        for c in gid:
            if c not in "0123456789abcdef":
                return True
        if not os.path.exists("log/game%s.log"%gid):
            return True
        return False
    
    def perform_response(s):
        """Respond to a GET request."""
        global games
        
        game = None
        player = None
        turn = None
        gid = None
        path = s.path
        if s.path.startswith("/gid"):
            gid = s.path[4:20]
            if gid in games:
                game, player, turn = games[gid]
            path = s.path[20:]
        
        if s.path == "/hanabiui.png":
            f = open("hanabiui.png", "rb")
            s.send_response(200)
            s.send_header("Content-type", "image/png")
            s.end_headers()
            shutil.copyfileobj(f, s.wfile)
            f.close()
            return
        
        if s.path.startswith("/favicon"):
            s.send_response(200)
            s.end_headers()
            return
            
        # I honestly don't know why, but I already a request for http://www.google.com
        if s.path.startswith("http://"): 
            s.send_response(400)
            s.end_headers()
            return
            
        if s.path.startswith("/robots.txt"):
            s.send_response(200)
            s.send_header("Content-type", "text/plain")
            s.end_headers()
            s.wfile.write("User-agent: *\n")
            s.wfile.write("Disallow: /\n")
            return
            
        
        
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
        
        
        if path.startswith("/tutorial"):
            gid = s.getgid()
            todelete = []
            try:
                for g in participantstarts:
                    if participantstarts[g] + 7200 < time.time():
                        todelete.append(g)
                for d in todelete:
                    del participants[d]
                    del participantstarts[d]
            except Exception:
                errlog.write("Error cleaning participants:\n")
                errlog.write(traceback.format_exc())
            participants[gid] = file("log/survey%s.log"%gid, "w")
            participantstarts[gid] = time.time()
            
            s.wfile.write("<html><head><title>Hanabi</title></head>")
            s.wfile.write('<body><center>')
            s.wfile.write(tutorial.intro)
            
            s.wfile.write('<form action="/tutorialdone" method="POST"><input type="hidden" value="%s" name="gid"/><input type="submit" value="Continue"/></form>'%(gid))
            
            s.wfile.write(tutorial.summary)
            
            s.wfile.write('</center></body></html>')
            return
            
        if s.path.startswith("/postsurvey/"):
            gid = s.path[12:]
            if gid in participants:
                s.postsurvey(gid)
            return
            
            
        if s.path.startswith("/consent") or s.path == "/":
            s.consentform()
            return
        
        if path.startswith("/new/study/"):
            oldgid = path[11:]
            if s.invalid(oldgid):
                s.wfile.write("<html><head><title>Hanabi</title></head>\n")
                s.wfile.write('<body><h1>Invalid Game ID</h1>\n')
                s.wfile.write("</body></html>")
                return
            
            gid = s.getgid()
            
            treatments = [("intentional", 1), ("intentional", 2), ("intentional", 3), ("intentional", 4), ("intentional", 5),
                          ("outer", 1), ("outer", 2), ("outer", 3), ("outer", 4), ("outer", 5),
                          ("full", 1), ("full", 2), ("full", 3), ("full", 4), ("full", 5)]
            random.seed(None)
            t = random.choice(treatments)
            nr = random.randint(6,10000)
            type = t[0]
            t = (type,nr)
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            log = file("log/game%s.log"%gid, "w")
            print >>log, "Old GID:", oldgid
            print >>log, "Treatment:", t
            random.seed(nr)
            game = hanabi.Game([ai,player], log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.started = False
            game.study = True
            todelete = []
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game,player,turn)
            
            
        
        elif path.startswith("/new/") and debug:
            
        
            type = s.path[5:]
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            gid = s.getgid()
            log = file("log/game%s.log"%gid, "w")
            print >>log, "Treatment:", type
            game = hanabi.Game([ai,player], log=log, format=1)
            game.treatment = type
            game.ping = time.time()
            game.started = False
            todelete = []
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game,player,turn)
        
            
        
        if gid is None or game is None or path.startswith("/restart/"):
            s.wfile.write("<html><head><title>Hanabi</title></head>\n")
            s.wfile.write('<body><h1>Invalid Game ID</h1>\n')
            s.wfile.write("</body></html>")
            return
            if game is not None:
                del game
            if gid is not None and gid in games:
                del games[gid]
            s.wfile.write("<html><head><title>Hanabi</title></head>\n")
            s.wfile.write('<body><h1>Welcome to Hanabi</h1> <p>To start, choose an AI:</p>\n')
            s.wfile.write('<ul><li><a href="/new/random">Random</a></li>\n')
            s.wfile.write('<li><a href="/new/inner">Inner State</a></li>\n')
            s.wfile.write('<li><a href="/new/outer">Outer State</a></li>\n')
            s.wfile.write('<li><a href="/new/self">Self Recognition</a></li>\n')
            s.wfile.write('<li><a href="/new/intentional">Intentional Player</a></li>\n')
            s.wfile.write('<li><a href="/new/full">Fully Intentional Player</a></li>\n')
            
            return
            
        if path.startswith("/explain") and debug:
            s.show_explanation(game)
            return 
            
        if path.startswith("/start/"):
            game.single_turn()
            game.started = True
            
        
        parts = path.strip("/").split("/")
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
                games[gid] = (game,player,turn)
                game.external_turn(action)
                game.single_turn()
            
                
                
        
        s.wfile.write("<html><head><title>Hanabi</title></head>")
        s.wfile.write('<body>')
        
        s.wfile.write(show_game_state(game, player, turn, gid))
       
        s.wfile.write("</body></html>")
        if game.done() and gid is not None and gid in games:
            errlog.write("%s game done. Score: %d\n"%(str(game.treatment), game.score()))
            errlog.flush()
            game.finish()
            del[gid]
        
    def show_explanation(s, game):
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
        
    def add_choice(s, name, question, answers, default=-1):
        s.wfile.write("<p>")
        s.wfile.write(question + "<br/>")
        s.wfile.write('<fieldset id="%s">\n'%name)
        for i,(aname,text) in enumerate(answers):
             if i == default:
                 s.wfile.write('<input name="%s" type="radio" value="%s" checked="checked">%s</option><br/>\n'%(name,aname,text))
             else:
                 s.wfile.write('<input name="%s" type="radio" value="%s">%s</option><br/>\n'%(name,aname,text))
        s.wfile.write("</fieldset>\n")
        s.wfile.write("</p>")
        
    def add_question(s, name, question):
        s.wfile.write("<p>")
        s.wfile.write(question + "<br/>")
        s.wfile.write('<input name="%s"/>\n'%name)
        s.wfile.write("</p>")
        
    def presurvey(s, gid, warn=False):
        s.wfile.write('<center><h1>Finally, please answer some question about previous board game experience</h1>')
        s.wfile.write('<table width="600px">\n<tr><td>')
        s.wfile.write('<form action="/submitpost2" method="POST">')
        s.add_choice("age", "What is your age?", [("20s", "18-29 years"), ("30s", "30-39 years"), ("40s", "40-49 years"), ("50s", "50-64 years"), ("na", "Prefer not to answer")])
        s.add_choice("bgg", "How familiar are you with the board and card games in general?", 
                            [("new", "I never play board or card games"),
                             ("dabbling", "I rarely play board or card games"),
                             ("intermediate", "I sometimes play board or card games"),
                             ("expert", "I often play board or card games")])
        s.add_choice("gamer", "Do you consider yourself to be a (board) gamer?", 
                            [("yes", "Yes"),
                             ("no", "No")])
        s.add_choice("exp", "How familiar are you with the card game Hanabi?", 
                            [("new", "I have never played before participating in this experiment"),
                             ("dabbling", "I have played a few (1-10) times"),
                             ("intermediate", "I have played multiple (10-50) times"),
                             ("expert", "I have played many (&gt; 50) times")])
        s.add_choice("recent", "When was the last time that you played Hanabi before this experiment?", 
                            [("never", "I have never played before or can't remember when I played the last time"),
                             ("long", "The last time I played has been a long time (over a year) ago"),
                             ("medium", "The last time I played has been some time (between 3 months and a year) ago"),
                             ("recent", "The last time I played was recent (up to 3 months ago)")])
        s.add_choice("score", "How often do you typically reach the top score of 25 in Hanabi?", 
                              [("never", "I never reach the top score, or I have never played Hanabi"),
                               ("few", "I almost never reach the top score (about one in 50 or more games)"),
                               ("sometimes", "I sometimes reach the top score (about one in 6-20 games)"),
                               ("often", "I often reach the top score (about one in 5 or fewer games)")])
        s.add_choice("publish", "Do you agree that the answers you provided and a log of the actions you performed in the game you played are made publicly available? This data will be completely anonymous and <b>not</b> include any other information such as an IP address that could be linked back to you.", 
                              [("yes", "Yes"),
                               ("no", "No")], 0)
        s.wfile.write("<p>")
        s.wfile.write('<input name="gid" type="hidden" value="%s"/>\n'%gid)
        s.wfile.write('<input type="submit" value="Continue"/>\n')
        s.wfile.write('</form></td></tr></table></center>')
        
    def postsurvey(s, gid, warn=False):
        s.wfile.write('<center><h1>Please answer some questions about your experience with the AI</h1>')
        s.wfile.write('<table width="600px">\n<tr><td>')
        s.wfile.write('<form action="/submitpost" method="POST">')
        
        s.add_choice("intention", "How intentional/goal-directed did you think this AI was playing?", 
                            [("1", "Never performed goal-directed actions"),
                             ("2", "Rarely performed goal-directed actions"),
                             ("3", "Sometimes performed goal-directed actions"),
                             ("4", "Often performed goal-directed actions"),
                             ("5", "Always performed goal-directed actions")])
        s.add_choice("skill", "How would you rate the play skill of this AI?", 
                              [("vbad", "The AI played very badly"),
                               ("bad", "The AI played badly"),
                               ("ok", "The AI played ok"),
                               ("good", "The AI played well"),
                               ("vgood", "The AI played very well")])
        s.add_choice("like", "How much did you enjoy playing with this AI?", 
                              [("vhate", "I really disliked playing with this AI"),
                               ("hate", "I somewhat disliked playing with this AI"),
                               ("neutral", "I neither liked nor disliked playing with this AI"),
                               ("like", "I somewhat liked playing with this AI"),
                               ("vlike", "I really liked playing with this AI")])
        s.wfile.write("<p>")
        s.wfile.write('<input name="gid" type="hidden" value="%s"/>\n'%gid)
        s.wfile.write('<input type="submit" value="Finish"/>\n')
        s.wfile.write('</form></td></tr></table></center>')
        
    def parse_POST(self):
        ctype, pdict = parse_header(self.headers['content-type'])
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = parse_qs(
                    self.rfile.read(length), 
                    keep_blank_values=1)
        else:
            postvars = {}
        return postvars
        
    def getgid(s):
        peer = str(s.connection.getpeername()) + str(time.time()) + str(os.urandom(4))
        return hashlib.sha224(peer).hexdigest()[:16]
        
    def do_POST(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
        tvars = s.parse_POST()
        vars = {}
        for v in tvars:
            vars[v] = tvars[v][0]
        if s.path.startswith("/submitpost2"):
            required = ["score", "age", "recent", "exp", "bgg", "gamer", "publish"]
            
            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]

            if gid not in participants:
                print >>errlog, gid, "not in participants", participants
                return s.presurvey(gid)
            
            for r in required:
                if r in vars:
                    print >> participants[gid], r, vars[r]
                
            participants[gid].close()
            
            s.wfile.write("<html><head><title>Hanabi</title></head>")
            s.wfile.write('<body><center>')
            s.wfile.write("<h1>Thank you for your participation in this study!</h1>")
            
            s.wfile.write('<a href="/new/study/%s">Play again</a><br/>(You can bookmark this link and play again at any later time. <br/>Any additional games you play will also be recorded for future analysis)'%(gid))
            
            s.wfile.write('</body></html>')
            del participants[gid]
            del participantstarts[gid]
            
            
        elif s.path.startswith("/tutorialdone"):
            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]
            if gid not in participants:
                participants[gid] = file("log/survey%s.log"%gid, "w")
                participantstarts[gid] = time.time()
            treatments = [("intentional", 1), ("intentional", 2), ("intentional", 3), ("intentional", 4), ("intentional", 5),
                          ("outer", 1), ("outer", 2), ("outer", 3), ("outer", 4), ("outer", 5),
                          ("full", 1), ("full", 2), ("full", 3), ("full", 4), ("full", 5)]
            random.seed(None)
            t = random.choice(treatments)            
            type = t[0]
            if type in ais:
                ai = ais[type](type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            log = file("log/game%s.log"%gid, "w")
            print >>log, "Treatment:", t
            random.seed(t[1])
            game = hanabi.Game([ai,player], log=log, format=1)
            game.treatment = t
            game.ping = time.time()
            game.dopostsurvey = True
            game.started = False
            todelete = []
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game,player,turn)
            s.wfile.write("<html><head><title>Hanabi</title></head>")
            s.wfile.write('<body>')
            
            s.wfile.write(show_game_state(game, player, turn, gid))
           
            s.wfile.write("</body></html>")
        elif s.path.startswith("/submitpost"):
            required = ["intention", "skill", "like"]
            
            gid = s.getgid()
            if "gid" in vars and vars["gid"]:
                gid = vars["gid"]

            if gid not in participants:
                s.wfile.write("<html><head><title>Hanabi</title></head>")
                s.wfile.write('<body><center>')
                s.wfile.write("<h1>Session timed out. Thank you for your time and participation</h1>")                
                s.wfile.write('</body></html>')
                return
            
            for r in required:
                if r in vars:
                    print >> participants[gid], r, vars[r]
            s.presurvey(gid)
            
        
    def consentform(s):
        s.wfile.write(consent.consent)
        s.wfile.write('<center><font size="12"><a href="/tutorial">By clicking here I agree to participate in the study</a></font></center><br/><br/><br/>')
        
 
if __name__ == '__main__':
    server_class = BaseHTTPServer.HTTPServer
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    errlog.write(time.asctime() + " Server Starts - %s:%s\n" % (HOST_NAME, PORT_NUMBER))
    errlog.flush()
    try:
       httpd.serve_forever()
    except KeyboardInterrupt:
     pass
    httpd.server_close()
    errlog.write(time.asctime() +  " Server Stops - %s:%s\n" % (HOST_NAME, PORT_NUMBER))
    errlog.flush()