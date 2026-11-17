package ru.cloverteam.stats;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.command.RemoteConsoleCommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.plugin.messaging.PluginMessageListener;
import org.bukkit.plugin.java.JavaPlugin;

import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import java.util.Base64;
import java.util.stream.Collectors;

public final class CloverTeamStats extends JavaPlugin
        implements CommandExecutor, Listener, PluginMessageListener {

    private static final Pattern MC_NAME = Pattern.compile("^[A-Za-z0-9_]{3,16}$");
    private static final String HELLO_CHANNEL = "cloverteam:hello";
    private static final String HELLO_ACK_CHANNEL = "cloverteam:hello_ack";
    private static final String SG_REQUEST_CHANNEL = "cloverteam:sg_request";
    private static final String SG_ACK_CHANNEL = "cloverteam:sg_ack";

    private final Set<UUID> verifiedClients = ConcurrentHashMap.newKeySet();

    @Override
    public void onEnable() {
        getLogger().info("CloverTeamStats enabled!");

        if (getCommand("cloverstats") == null
                || getCommand("cloverwarn") == null
                || getCommand("cloversg") == null) {
            getLogger().severe("Required commands were not found in plugin.yml!");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        getCommand("cloverstats").setExecutor(this);
        getCommand("cloverwarn").setExecutor(this);
        getCommand("cloversg").setExecutor(this);
        getServer().getPluginManager().registerEvents(this, this);

        getServer().getMessenger().registerOutgoingPluginChannel(this, HELLO_CHANNEL);
        getServer().getMessenger().registerIncomingPluginChannel(this, HELLO_ACK_CHANNEL, this);
        getServer().getMessenger().registerOutgoingPluginChannel(this, SG_REQUEST_CHANNEL);
        getServer().getMessenger().registerIncomingPluginChannel(this, SG_ACK_CHANNEL, this);

        for (Player player : Bukkit.getOnlinePlayers()) {
            sendHello(player);
        }
    }

    @Override
    public void onDisable() {
        getServer().getMessenger().unregisterIncomingPluginChannel(this);
        getServer().getMessenger().unregisterOutgoingPluginChannel(this);
        verifiedClients.clear();
        getLogger().info("CloverTeamStats disabled!");
    }

    @EventHandler
    public void onPlayerJoin(PlayerJoinEvent event) {
        verifiedClients.remove(event.getPlayer().getUniqueId());
        Bukkit.getScheduler().runTaskLater(this, () -> sendHello(event.getPlayer()), 20L);
    }

    private void sendHello(Player player) {
        if (!player.isOnline()) return;
        player.sendPluginMessage(this, HELLO_CHANNEL, new byte[0]);
    }

    @Override
    public void onPluginMessageReceived(String channel, Player player, byte[] message) {
        if (HELLO_ACK_CHANNEL.equals(channel)) {
            verifiedClients.add(player.getUniqueId());
            getLogger().info("CloverTeam Client handshake received from " + player.getName());
            return;
        }

        if (SG_ACK_CHANNEL.equals(channel)) {
            getLogger().info("ScreenGrab notification acknowledged by " + player.getName());
        }
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        boolean isConsole = sender instanceof ConsoleCommandSender
                || sender instanceof RemoteConsoleCommandSender;
        if (!isConsole) {
            sender.sendMessage("This command can only be executed by console or RCON.");
            return true;
        }

        return switch (command.getName().toLowerCase()) {
            case "cloverstats" -> handleStats(sender);
            case "cloverwarn" -> handleWarn(sender, args);
            case "cloversg" -> handleScreenGrab(sender, args);
            default -> true;
        };
    }

    private boolean handleStats(CommandSender sender) {
        Collection<? extends Player> online = Bukkit.getOnlinePlayers();
        int players = online.size();
        long ops = online.stream().filter(Player::isOp).count();
        List<String> names = online.stream().map(Player::getName).collect(Collectors.toList());
        String playerNames = names.isEmpty() ? "-" : String.join(", ", names);
        sender.sendMessage("CLOVER_STATS players=" + players + " ops=" + ops + " names=" + playerNames);
        return true;
    }

    private boolean handleScreenGrab(CommandSender sender, String[] args) {
        if (args.length != 1 || !MC_NAME.matcher(args[0]).matches()) {
            sender.sendMessage("Usage: cloversg <player>");
            return true;
        }

        Player target = Bukkit.getPlayerExact(args[0]);
        if (target == null) {
            sender.sendMessage("CLOVER_SG_ERROR player_offline");
            return true;
        }

        if (!verifiedClients.contains(target.getUniqueId())) {
            sendHello(target);
            sender.sendMessage("CLOVER_SG_ERROR client_mod_missing_or_not_ready");
            return true;
        }

        target.sendPluginMessage(this, SG_REQUEST_CHANNEL, new byte[0]);
        sender.sendMessage("CLOVER_SG_QUEUED player=" + target.getName());
        getLogger().info("ScreenGrab notification requested for " + target.getName());
        return true;
    }

    private boolean handleWarn(CommandSender sender, String[] args) {
        if (args.length != 3) {
            sender.sendMessage("Usage: cloverwarn <player> <days|PERMANENT> <reasonBase64>");
            return true;
        }

        String playerName = args[0];
        String duration = args[1];
        String encodedReason = args[2];

        if (!MC_NAME.matcher(playerName).matches()) {
            sender.sendMessage("Invalid Minecraft nickname.");
            return true;
        }

        boolean permanent = duration.equalsIgnoreCase("PERMANENT");
        if (!permanent) {
            try {
                if (Integer.parseInt(duration) <= 0) {
                    sender.sendMessage("Invalid duration.");
                    return true;
                }
            } catch (NumberFormatException exception) {
                sender.sendMessage("Invalid duration.");
                return true;
            }
        }

        String reason;
        try {
            String normalized = encodedReason;
            while (normalized.length() % 4 != 0) normalized += "=";
            reason = new String(Base64.getUrlDecoder().decode(normalized), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException exception) {
            sender.sendMessage("Invalid warning reason encoding.");
            return true;
        }

        if (reason.isBlank() || reason.length() > 350) {
            sender.sendMessage("Invalid warning reason.");
            return true;
        }

        Component announcement = Component.text("[TLG] ").color(NamedTextColor.AQUA)
                .append(Component.text(playerName).color(NamedTextColor.YELLOW))
                .append(Component.text(" получил варн на ").color(NamedTextColor.GRAY));

        announcement = announcement.append(permanent
                ? Component.text("ПЕРМАНЕНТНО").color(NamedTextColor.RED)
                : Component.text(duration + " дн.").color(NamedTextColor.GRAY));

        announcement = announcement
                .append(Component.text(" по причине: ").color(NamedTextColor.GRAY))
                .append(Component.text(reason).color(NamedTextColor.WHITE));

        Bukkit.broadcast(announcement);
        sender.sendMessage("CLOVER_WARN_OK player=" + playerName);
        getLogger().info("Warning announcement sent for " + playerName + ", duration=" + duration);
        return true;
    }
}
