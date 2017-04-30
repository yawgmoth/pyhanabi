

intro = """
<h1>Short introduction to the Hanabi User Interface</h1>
<table width="800px"><tr><td>
<p>You will play a game of the card game Hanabi in a browser-based implementation. This tutorial will describe how to use the user interface, so please read it carefully.</p>
<p>If you are not familiar with the card game Hanabi or need a refresher on the rules, you can read a short summary at the end of this page or refer to the official rules <a href="http://www.regatuljocurilor.ro/product_extra_files/HanabiRules-EnglishTransofFrench-1page.pdf" target="_blank">here</a>
<p>The user interface you will be playing in looks like this:
<p><img src="/hanabiui.png"/></p>
<p>On the left you can see how many hint tokens are currently available, how many mistakes have been made so far and how many cards are left in the deck. If you reach 2 mistakes, as in the picture above, the number will turn red and be shown in bold to draw your attention to that fact. 
</p>
<p>In the center you see the AI player's hand on top, the board in the center and a representation of your hand (which you can't see) on the bottom. To play or discard one of your own cards, click the link
on that card to do so. To hint the AI about all their cards of a particular color or rank, click the link on any card that matches that color or rank. For example, if you click the "hint color" link on the yellow 4, they
will be hinted about all their yellow cards. <b>Note that the "Hint Color" and "Hint Rank" links will not be shown when no hint tokens are available.</b> Underneath each card in your hand you can see what you have been told about that card in the past. The same goes for the cards in the AI's hand. Note that you will not be reminded
of information that you can infer from a hint. In particular, if you are told that some of your cards are 1s, they will be marked as such, but the other cards will <b>not</b> be marked as "not 1s". </p>

<p>On the right side of the screen, finally, you will see the last actions that happened, with the newest action on top of the list. The cards that were affected by the last two actions (your last action and the last action the AI performed) will also be highlighted in red. For hints that were given this will appear as a red frame around the card or cards in a player's hand. For a card that was successfully played a red frame will be drawn around the stack on the board on which the card was played. Otherwise, if a card is unsuccessfully played or discarded, that card will be highlighted in red in the list of cards in the trash.</p>

<p>When you click "Continue" you and the AI will immediately be dealt cards. When you click "Start Game" the AI will take the first turn, and then it is your turn.
</td></tr></table>
"""

summary = """
<h2>Hanabi rules summary</h2>
<table width="800px"><tr><td>
<p>Hanabi is a cooperative card game in which you don't see your own cards, but you see the cards the other player has in their hand. There are 5 colors in the game: yellow, red, blue, green and white, and each color has cards in the ranks 1 to 5. Each color has three copies of the 1s, two copies of the 2s, 3s and 4s and only a single copy of the 5s.</p>

<p>The goal of the game is to play the cards on five stacks, one for each color, in ascending order, starting with the 1s. At the end of the game you will receive one point for each card that was successfully played.</p>
<p>On your turn you have the choice between one of three actions:
<ul>
<li> <b>Play a card:</b> Choose a card from your hand and play it. If it is the next card in ascending order for any stack on the board, it will be placed there, otherwise it will be counted as a mistake and the car will be put in the trash.
<li> <b>Give a hint:</b> Tell the other player about <b>all</b> cards in their hand that have a particular color or a particular rank. For example, you can tell the other player which of their cards are yellow, but you have to tell them all their yellow cards. Likewise, if you want to tell the other player which of their cards are 3s, you have to tell them all their 3s. You can also not tell them that they have zero of a particular color or rank. Giving a hint consumes one hint token, of which there are initially 8.
<li> <b>Discard a card:</b> Choose a card from your hand and put it in the trash pile. This will regenerate one hint token, but you can never have more than the initial 8.
</ul>
The game lasts until either the last card is drawn, plus one additional turn for each player, or until 3 mistakes have been made.
</td></tr></table>
"""

