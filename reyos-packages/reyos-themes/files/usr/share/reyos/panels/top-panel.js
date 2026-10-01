// ReyOS top bar, macOS-style (shared by reyos-apply-branding.sh and
// reyos-apply-top-panel.sh). Left: ReyOS system menu, active app icon + name,
// the app's global menu. Right: workspace dots, tray, date and time.
var t = new Panel;
t.location = "top";
t.height = 30;
t.floating = false;
t.immutability = 3;
t.addWidget("org.reyos.systemmenu");
var title = t.addWidget("com.github.antroids.application-title-bar");
title.currentConfigGroup = ["Appearance"];
title.writeConfig("widgetElements", "windowIcon,windowTitle");
title.writeConfig("windowTitleSource", "0");
title.writeConfig("windowTitleUndefined", "ReyOS");
title.writeConfig("windowTitleMarginsLeft", "6");
title.writeConfig("windowTitleMarginsRight", "4");
t.addWidget("org.kde.plasma.appmenu");
t.addWidget("org.kde.plasma.panelspacer");
t.addWidget("org.reyos.workspacedots");
var tray = t.addWidget("org.kde.plasma.systemtray");
tray.currentConfigGroup = ["General"];
tray.writeConfig("shownItems", "org.kde.plasma.notifications,org.kde.plasma.clipboard,org.kde.plasma.bluetooth,org.kde.plasma.volume,org.kde.plasma.networkmanagement,org.kde.plasma.battery");
var clock = t.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", "true");
clock.writeConfig("dateFormat", "custom");
clock.writeConfig("customDateFormat", "ddd MMM d");
clock.writeConfig("dateDisplayFormat", "BesideTime");
