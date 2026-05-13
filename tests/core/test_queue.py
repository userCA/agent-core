from agent_core.core.queue import PendingMessageQueue


def test_queue_one_at_a_time():
    q = PendingMessageQueue(mode="one-at-a-time")
    q.enqueue("a")
    q.enqueue("b")
    assert q.has_items()
    assert q.drain() == ["a"]
    assert q.drain() == ["b"]
    assert q.drain() == []


def test_queue_drain_all():
    q = PendingMessageQueue(mode="all")
    q.enqueue("a")
    q.enqueue("b")
    assert q.drain() == ["a", "b"]
    assert q.has_items() is False


def test_queue_clear():
    q = PendingMessageQueue(mode="all")
    q.enqueue("a")
    q.clear()
    assert q.has_items() is False


def test_queue_mode_can_be_set():
    q = PendingMessageQueue(mode="all")
    q.mode = "one-at-a-time"
    q.enqueue("a")
    q.enqueue("b")
    assert q.drain() == ["a"]
