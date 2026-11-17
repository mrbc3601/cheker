package ru.cloverteam.client;

import net.fabricmc.api.ClientModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Main client entrypoint.
 *
 * This initial version only establishes the Fabric project skeleton.
 * Player-screen capture and upload features are intentionally not implemented
 * in this bootstrap.
 */
public final class CloverTeamClient implements ClientModInitializer {
    public static final String MOD_ID = "cloverteam_client";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitializeClient() {
        LOGGER.info("CloverTeam Client initialized.");
    }
}
