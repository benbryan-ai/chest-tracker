# Writing a notice

The app reads `notices.json` from the `main` branch of this repository (about every couple of hours) and shows
the messages that are active. Edit the file on GitHub and commit; no release is needed. Example:

```json
{
  "schema": 1,
  "notices": [
    {
      "id": "fortnite-update-2026-11",
      "level": "warning",
      "title": "Fortnite update",
      "text": "The latest Fortnite update stopped replay counting from working. A fix is coming.",
      "from": "2026-11-20T00:00:00Z",
      "to": "2026-11-27T00:00:00Z",
      "minVersion": "1.2.0",
      "maxVersion": "1.6.0"
    }
  ]
}
```

- `id` (required, up to 60 characters): each person can dismiss a notice, and a new `id` shows it again.
- `text` (required, up to 400 characters) and `title` (optional, up to 80): plain text only.
- `level`: `info` or `warning`.
- `from` / `to` (optional): when to show it; include the time zone, like the `Z` above.
- `minVersion` / `maxVersion` (optional): only show it to those app versions.
- Up to 10 notices are read. A notice with a mistake is skipped, and an empty list (`"notices": []`) shows nothing.
