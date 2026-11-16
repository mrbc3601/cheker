
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
import org.bukkit.plugin.java.JavaPlugin;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Collection;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public final class CloverTeamStats extends JavaPlugin
        implements CommandExecutor {

    private static final Pattern MC_NAME =
            Pattern.compile("^[A-Za-z0-9_]{3,16}$");

    @Override
    public void onEnable() {

        getLogger().info("CloverTeamStats enabled!");

        if (getCommand("cloverstats") == null
                || getCommand("cloverwarn") == null) {

            getLogger().severe(
                    "Required commands were not found in plugin.yml!"
            );

            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        getCommand("cloverstats").setExecutor(this);
        getCommand("cloverwarn").setExecutor(this);
    }

    @Override
    public void onDisable() {
        getLogger().info("CloverTeamStats disabled!");
    }

    @Override
    public boolean onCommand(
            CommandSender sender,
            Command command,
            String label,
            String[] args
    ) {

        boolean isConsole =
                sender instanceof ConsoleCommandSender;

        boolean isRemoteConsole =
                sender instanceof RemoteConsoleCommandSender;

        if (!isConsole && !isRemoteConsole) {

            sender.sendMessage(
                    "This command can only be executed by console or RCON."
            );

            return true;
        }

        if (command.getName().equalsIgnoreCase("cloverstats")) {
            return handleStats(sender, args);
        }

        if (command.getName().equalsIgnoreCase("cloverwarn")) {
            return handleWarn(sender, args);
        }

        return true;
    }

    // =================================================
    // CLOVER STATS
    // =================================================

    private boolean handleStats(
            CommandSender sender,
            String[] args
    ) {

        Collection<? extends Player> online =
                Bukkit.getOnlinePlayers();

        int players = online.size();

        long ops = online.stream()
                .filter(Player::isOp)
                .count();

        List<String> names = online.stream()
                .map(Player::getName)
                .collect(Collectors.toList());

        String playerNames = names.isEmpty()
                ? "-"
                : String.join(", ", names);

        String response =
                "CLOVER_STATS players=" + players
                        + " ops=" + ops
                        + " names=" + playerNames;

        sender.sendMessage(response);

        return true;
    }

    // =================================================
    // CLOVER WARN
    // =================================================

    private boolean handleWarn(
            CommandSender sender,
            String[] args
    ) {

        if (args.length != 3) {

            sender.sendMessage(
                    "Usage: cloverwarn <player> <days|PERMANENT> <reasonBase64>"
            );

            return true;
        }

        String playerName = args[0];
        String duration = args[1];
        String encodedReason = args[2];

        if (!MC_NAME.matcher(playerName).matches()) {

            sender.sendMessage(
                    "Invalid Minecraft nickname."
            );

            return true;
        }

        boolean permanent =
                duration.equalsIgnoreCase("PERMANENT");

        if (!permanent) {

            try {
                int days = Integer.parseInt(duration);

                if (days <= 0) {
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

            while (normalized.length() % 4 != 0) {
                normalized += "=";
            }

            byte[] decoded = Base64.getUrlDecoder()
                    .decode(normalized);

            reason = new String(
                    decoded,
                    StandardCharsets.UTF_8
            );

        } catch (IllegalArgumentException exception) {

            sender.sendMessage(
                    "Invalid warning reason encoding."
            );

            return true;
        }

        if (reason.isBlank() || reason.length() > 350) {

            sender.sendMessage(
                    "Invalid warning reason."
            );

            return true;
        }

        Component announcement = Component.text("[TLG] ")
                .color(NamedTextColor.AQUA)

                .append(
                        Component.text(playerName)
                                .color(NamedTextColor.YELLOW)
                )

                .append(
                        Component.text(" получил варн на ")
                                .color(NamedTextColor.GRAY)
                );

        if (permanent) {

            announcement = announcement.append(
                    Component.text("ПЕРМАНЕНТНО")
                            .color(NamedTextColor.RED)
            );

        } else {

            announcement = announcement.append(
                    Component.text(duration + " дн.")
                            .color(NamedTextColor.GRAY)
            );
        }

        announcement = announcement

                .append(
                        Component.text(" по причине: ")
                                .color(NamedTextColor.GRAY)
                )

                .append(
                        Component.text(reason)
                                .color(NamedTextColor.WHITE)
                );

        Bukkit.broadcast(announcement);

        sender.sendMessage(
                "CLOVER_WARN_OK player=" + playerName
        );

        getLogger().info(
                "Warning announcement sent for "
                        + playerName
                        + ", duration="
                        + duration
        );

        return true;
    }
}
