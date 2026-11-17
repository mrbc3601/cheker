package ru.cloverteam.client;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Client entrypoint and first-stage CloverTeam server handshake.
 *
 * Screen capture and image upload are deliberately not part of this bootstrap.
 * Any later capture flow must display a visible notice before capturing.
 */
public final class CloverTeamClient implements ClientModInitializer {
    public static final String MOD_ID = "cloverteam_client";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private static final CustomPayload.Id<HelloPayload> HELLO_ID =
            new CustomPayload.Id<>(Identifier.of("cloverteam", "hello"));
    private static final CustomPayload.Id<HelloAckPayload> HELLO_ACK_ID =
            new CustomPayload.Id<>(Identifier.of("cloverteam", "hello_ack"));
    private static final CustomPayload.Id<ScreenGrabRequestPayload> SG_REQUEST_ID =
            new CustomPayload.Id<>(Identifier.of("cloverteam", "sg_request"));
    private static final CustomPayload.Id<ScreenGrabAckPayload> SG_ACK_ID =
            new CustomPayload.Id<>(Identifier.of("cloverteam", "sg_ack"));

    private static final PacketCodec<RegistryByteBuf, HelloPayload> HELLO_CODEC =
            PacketCodec.unit(new HelloPayload());
    private static final PacketCodec<RegistryByteBuf, HelloAckPayload> HELLO_ACK_CODEC =
            PacketCodec.unit(new HelloAckPayload());
    private static final PacketCodec<RegistryByteBuf, ScreenGrabRequestPayload> SG_REQUEST_CODEC =
            PacketCodec.unit(new ScreenGrabRequestPayload());
    private static final PacketCodec<RegistryByteBuf, ScreenGrabAckPayload> SG_ACK_CODEC =
            PacketCodec.unit(new ScreenGrabAckPayload());

    @Override
    public void onInitializeClient() {
        PayloadTypeRegistry.playS2C().register(HELLO_ID, HELLO_CODEC);
        PayloadTypeRegistry.playC2S().register(HELLO_ACK_ID, HELLO_ACK_CODEC);
        PayloadTypeRegistry.playS2C().register(SG_REQUEST_ID, SG_REQUEST_CODEC);
        PayloadTypeRegistry.playC2S().register(SG_ACK_ID, SG_ACK_CODEC);

        ClientPlayNetworking.registerGlobalReceiver(HELLO_ID, (payload, context) -> {
            LOGGER.info("CloverTeam server handshake received");
            ClientPlayNetworking.send(new HelloAckPayload());
        });

        ClientPlayNetworking.registerGlobalReceiver(SG_REQUEST_ID, (payload, context) -> {
            // The request is announced visibly before any future capture code.
            context.client().inGameHud.setOverlayMessage(
                    Text.literal("Выполняется ScreenGrab"), false);
            ClientPlayNetworking.send(new ScreenGrabAckPayload());
            LOGGER.info("Visible ScreenGrab request notification displayed");
        });

        LOGGER.info("CloverTeam Client initialized");
    }

    private record HelloPayload() implements CustomPayload {
        @Override
        public Id<HelloPayload> getId() {
            return HELLO_ID;
        }
    }

    private record HelloAckPayload() implements CustomPayload {
        @Override
        public Id<HelloAckPayload> getId() {
            return HELLO_ACK_ID;
        }
    }

    private record ScreenGrabRequestPayload() implements CustomPayload {
        @Override
        public Id<ScreenGrabRequestPayload> getId() {
            return SG_REQUEST_ID;
        }
    }

    private record ScreenGrabAckPayload() implements CustomPayload {
        @Override
        public Id<ScreenGrabAckPayload> getId() {
            return SG_ACK_ID;
        }
    }
}
