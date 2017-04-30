# A platform for the exploration and evaluation of Hanabi AIs

## Synopsis

This repository contains an implementation of the card game [Hanabi](https://boardgamegeek.com/boardgame/98778/hanabi) with several different AIs. It can be used to see how current AIs perform, as well as to develop new AIs, including testing them with human cooperators.

## Usage

Our implementation has two modes of operation: A graphical one, running inside a web-browser, and a command-line option. To use the graphical interface, run:

```python httpui.py```

and open http://127.0.0.1:31337/ in a web browser. The command line version of the tool is run with

```python hanabi.py <players>```

where `<players>` is a space-separated list of AI names. Refer to `hanabi.py` to see valid names for AIs and general usage. We recommend using the graphical interface for playing the game and general development and restrict using the command line option to run simulations of AI/AI games.

## Extension

Our implementation was built with extensibility in mind. `hanabi.py` already contains 8 different AIs, some are implementations of the AIs presented in "Solving Hanabi: Estimating Hands by Opponent's Actions in Cooperative Game with Incomplete Information" (Osawa, Hirotaka, in the proceedings of Workshops at the Twenty-Ninth AAAI Conference on Artificial Intelligence, 2015), while others are our own development, two of which are presented in "An Intentional AI for Hanabi" (Eger, Markus and Martens, Chris and Alfaro Cordoba, Marcela, to appear). 

To add another AI, the process consists of two steps:
1. Subclass `Player`
2. Register the new AI

The first step involves implementing the methods `get_action` and `inform`. The former is called when it is the AI player's turn, and should return an Action object representing the action the player wants to perform (legal return values are passed as the `valid_actions` argument), while the latter is called to inform the agent of which actions are performed by the players. The second step adds the AI to the list of AIs the user can choose from in the UI. To do so, add the class to the dictionary `ais` in `httpui.py`, and to the enumeration of available AIs in the html, also in `httpui.py`. Searching for `AIClasses` and `AIList` helps with locating these two locations.

In addition to implementing the methods to play the game, each AI player class can also set the `explanation` member to a list of lists. This list will be rendered as a table when clicking on the "Explain" button in the user interface. This way it is possible to record and convey information that is helpful with debugging and/or understanding the AI. The `SelfIntentionalPlayer` uses this to show, among other things, which cards the human cooperator has and which intentions it has for them, what they know about their own hand and the utility of discarding a card. Having this information available during game play can greatly help with improving the AI.

### `get_action`
 
This is the core method of an AI, it is passed 8 parameters:
* `nr`: This is the 0-based index of the player that is currently making the decision as an integer.
* `hands`: This is a list of list of cards, where each sub-list represents the hand of a single player. Note that since a player can not see their own hand, `hands[nr]` is the empty list.
* `knowledge`: This is a list of player knowledge structures, representing what each player has been hinted about so far in the game. For every player, the knowledge structure is a list of card knowledge structures, one for each card in their hand. These card knowledge structures can then be indexed by a color and a 0-based rank to learn if a player thinks the card could be of this identity or not. For example, `knowledge[nr][0][GREEN][1]` contains a number greater than 0 if the current player considers it possible that the card at index 0 in their hand is the green 2 (since the rank is 0-based), or 0 otherwise.
* `trash`: This is a list of cards already in the trash (after being discarded or played without fitting on the board)
* `played`: This is a list of all cards that have been played successfully
* `board`: This is a list of cards that are currently on the top of each stack on the board. Empty stacks will have a 0 on top, making it possible to easily check what the next card should be for each color. This is provided as a convenience only, since it could also be calculated from the information contained in `played`
* `valid_actions`: This is a list of valid actions. In particular, it will not contain hint actions if no hint tokens are available.
* `hints`: The number of hint tokens left.

The return value of this function should be one of the actions in `valid_action`. It is not actually enforced that the AI returns one of these objects, it is equally permissible to construct a new action object with valid parameters. Note that the game currently does not enforce that the AI does not cheat by returning a hint action when no hint tokens are available. 

### Convenience functions

The following functions can be useful when developing a new AI:

* `get_possible` takes a card knowledge structure as its argument and returns a list of all identities the card corresponding to the knowledge structure could have.
* `playable` takes a card knowledge structure and the board, as represented by the `board` parameter to `get_action` and returns `True` iff the card corresponding to the knowledge structure is guaranteed to be playable
* `discardable` takes a card knowledge structure and the board, as represented by the `board` parameter to `get_action` and returns `True` iff the card corresponding to the knowledge structure is guaranteed to be discardable (because it is lower than the next card that would need to be played in its color)
* `potentially_playable` and `potentially_discardable` are the same as `playable` and `discardable`, respectively, but return `True` if the card *may* be playable/discardable, even if it is not guaranteed
* `update_knowledge` takes a player knowledge structure (which is a list of card knowledge structures), and a list of cards `used`, and removes these cards from the possibilities. Initially, every entry in the knowledge structure contains the number of exemplars of the card corresponding to the entry, and this function decreases that count by one for each card in the list `used`. The use of this function is to update a player's knowledge by counting which cards have been played or discarded so far, and removing those possibilities from their knowledge base. For example, if a player knows that a card is red, the entries corresponding to the red 1 through 5 will be `[3, 2, 2, 2, 1]`, because there are three red 1s, two of each of the red 2s, 3s and 4s and one red 5. However, if both red 3s have been discarded already, the player can dismiss this possibility. The `update_knowledge` function is meant to be used to basically subtract the trash and the board from the knowledge to achieve this.


## Data Set

Our system can also be used to view replays of games, as well as taking over game play at any point during such a replay, even with a different AI. As an example for the use of this feature, we have obtained a data set, consisting of over 2000 game logs from 240 players, which is available in a [separate repository](https://github.com/yawgmoth/HanabiData). Simply place the game logs in the `log/` directory and they can be opened from the main menu of the UI.


## Disclaimer

Note that Hanabi was designed by Antoine Bauza and is published by Asmodée Éditions, who hold the rights to the game. Our implementation is provided for research purposes only!
