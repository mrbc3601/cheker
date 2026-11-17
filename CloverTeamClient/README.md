# CloverTeam Client

Client-side Fabric mod for Minecraft Java 1.21.11 and Java 21.

## Current stage

- Fabric client entrypoint and dependency metadata.
- Client/server payload channel definitions.
- Client handshake response for the Paper plugin.
- Visible in-game notification when a ScreenGrab request arrives.
- Acknowledgement that the notification was displayed.

**Not implemented yet:** screenshot capture, screenshot transfer to the bot, automatic installer, and a complete server-side mandatory-mod gate. The acknowledgement is not a screenshot receipt.

## Build

Install JDK 21 and Gradle 9.2 or newer. From this directory run:

```bash
gradle build
```

The remapped JAR will be created in `build/libs/`.

## Privacy

The intended feature is limited to the Minecraft game image. It must not capture the operating-system desktop or other applications. A visible in-game notice is required before any future capture.
