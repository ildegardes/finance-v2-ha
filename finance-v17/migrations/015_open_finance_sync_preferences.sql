CREATE TABLE of_sync_preferences (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    interval_hours INTEGER NOT NULL CHECK(interval_hours IN (1,2,4,6,12,24,48)),
    revision INTEGER NOT NULL CHECK(revision>0)
);
CREATE TABLE of_sync_preference_events (
    revision INTEGER PRIMARY KEY CHECK(revision>0),
    observed_at TEXT NOT NULL,
    actor TEXT NOT NULL CHECK(actor='UI:local'),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    interval_hours INTEGER NOT NULL CHECK(interval_hours IN (1,2,4,6,12,24,48))
);
