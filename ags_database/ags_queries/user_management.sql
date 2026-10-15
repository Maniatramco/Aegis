-- Read-only account inventory. Password hashes and CSRF/session tokens are omitted.
SELECT u.id AS user_id, u.username,
       u.role AS account_access,
       u.created_at, creator.username AS created_by,
       u.updated_at, updater.username AS updated_by,
       u.created_via, u.updated_via
FROM user_tbl u
LEFT JOIN user_tbl creator ON creator.id = u.created_by
LEFT JOIN user_tbl updater ON updater.id = u.updated_by
ORDER BY u.username;

-- Session counts only: expires stores Unix epoch seconds.
SELECT u.username, COUNT(s.id) AS stored_sessions
FROM user_tbl u
LEFT JOIN sessions_tbl s ON s.owner = u.id
GROUP BY u.username
ORDER BY u.username;
