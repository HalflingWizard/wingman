from types import SimpleNamespace

from wingman.telegram_bot import planning_list_view


def planning_record(identifier: str, title: str):
    return SimpleNamespace(id=identifier, name=title, title=title)


def test_places_menu_shows_five_items_and_next_button():
    records = [planning_record(str(index), f"Place {index}") for index in range(6)]

    text, keyboard = planning_list_view("place", records)

    assert "📍 Places · page 1 of 2" == text
    assert len(keyboard.inline_keyboard) == 6
    assert [button.text for button in keyboard.inline_keyboard[-1]] == ["Next ▶"]
    assert keyboard.inline_keyboard[0][0].callback_data == "planning:view:place:0:0"


def test_events_menu_shows_previous_and_next_on_middle_page():
    records = [planning_record(str(index), f"Event {index}") for index in range(11)]

    text, keyboard = planning_list_view("event", records, page=1)

    assert "📅 Events · page 2 of 3" == text
    assert [button.text for button in keyboard.inline_keyboard[-1]] == [
        "◀ Previous",
        "Next ▶",
    ]
    assert keyboard.inline_keyboard[0][0].text == "📅 Event 5"


def test_planning_menu_clamps_invalid_page():
    records = [planning_record("1", "One")]

    text, keyboard = planning_list_view("place", records, page=99)

    assert "page 1 of 1" in text
    assert len(keyboard.inline_keyboard) == 1


def test_ideas_and_reminders_use_their_own_icons_and_titles():
    idea = planning_record("idea-1", "Try a pasta bar")
    reminder = planning_record("reminder-1", "Call Chloe")

    idea_text, idea_keyboard = planning_list_view("idea", [idea])
    reminder_text, reminder_keyboard = planning_list_view("reminder", [reminder])

    assert "💡 Ideas" in idea_text
    assert idea_keyboard.inline_keyboard[0][0].text == "💡 Try a pasta bar"
    assert "⏰ Reminders" in reminder_text
    assert reminder_keyboard.inline_keyboard[0][0].text == "⏰ Call Chloe"
