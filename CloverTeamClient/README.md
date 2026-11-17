# CloverTeam Client

Client-side Fabric mod for CloverTeam.

## Target environment

- Minecraft Java Edition 1.21.11
- Java 21
- Fabric Loader 0.18.1
- Fabric API 0.141.6+1.21.11
- Fabric Loom 1.14.10

## Build

From this directory, with JDK 21 and Gradle 9.2 or newer installed:

```bash
gradle build
```

The distributable remapped mod JAR is produced in `build/libs/`.

## Current status

This is the initial project scaffold. It registers a client entrypoint and logs
when the mod loads. Server protocol, compatibility checks, and the installer
will be developed in later stages.

Any feature that captures a player's game screen must be clearly disclosed to
the player before capture. This scaffold does not implement screen capture.
