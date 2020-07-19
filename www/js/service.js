window.DRApp = new DoTRoute.Application();

DRApp.load = function (name) {
    return $.ajax({url: name + ".html", async: false}).responseText;
}

DRApp.password = $.cookie('klot-io-password');

if (!DRApp.password && window.location.hostname == "klot-io.local") {
    DRApp.password = "kloudofthings"
}

DRApp.STATUSES = {
    "Login": 0,
    "Uninitialized": 1,
    "Joined": 2,
    "Initializing": 3,
    "Creating": 4,
    "NotReady": 5,
    "Master": 6,
    "Workers": 7,
    "Apps": 8
};

DRApp.status =  "Login";

DRApp.controller("Base",null,{
    timeout: null,
    loading: function() {
        $("#spinner").show();
    },
    start: function() {
        this.stop();
        this.timeout = window.setTimeout($.proxy(this.update,this), 10000);
    },
    update: function() {
        if (!$("#name").is(":focus")) {
            this.application.refresh();
        } else {
            this.start();
        }
    },
    stop: function() {
        if (this.timeout) {
            window.clearTimeout(this.timeout);
        }
    },
    rest: function(type,url,data) {
        var response = $.ajax({
            type: type,
            url: url,
            contentType: "application/json",
            headers: {'x-klot-io-password': DRApp.password},
            data: (data === null) ? null : JSON.stringify(data),
            dataType: "json",
            async: false
        });
        if ((response.status != 200) && (response.status != 201) && (response.status != 202)) {
            alert(type + ": " + url + " failed\n" + response.responseText);
            throw (type + ": " + url + " failed");
        }
        return response.responseJSON;
    },
    update_status: function() {
        try {
            DRApp.status = this.rest("GET", "/api/status").status;
        } catch (err) {
            DRApp.status = "Login";
        }
        return DRApp.status;
    },
    home: function() {
        this.update_status();
        if (DRApp.status == "Login") {
            this.application.go("login");
        } else if (DRApp.status == "Uninitialized") {
            this.application.go("config");
        } else if (DRApp.STATUSES[DRApp.status] < DRApp.STATUSES["NotReady"]) {
            this.application.go("status");
        } else if (DRApp.status == "NotReady") {
            this.application.go("pods");
        } else if (DRApp.status == "Master") {
            this.application.go("nodes");
        } else if (DRApp.status == "Workers") {
            this.application.go("apps");
        } else {
            this.loading();
            this.update_status();
            this.it = {
                apps: this.rest("GET","/api/app").apps
            }
            this.application.render(this.it);
            this.start();
        }
    },
    login: function() {
        this.application.render(this.it);
    },
    password_enter: function(event) {
        if(event.keyCode === 13){
            event.preventDefault();
            this.password();
        }
    },
    password: function() {
        DRApp.password = $("#password").val();
        $.cookie('klot-io-password', DRApp.password);
        this.application.go("home");
    },
    logout: function() {
        DRApp.password = null;
        $.cookie('klot-io-password', DRApp.password);
        this.application.go("home");
    },
    logs: function() {
        this.loading();
        this.update_status();
        this.it = {
            lines: this.rest("GET","/api/log/" + this.application.current.path.service).lines
        };
        this.application.render(this.it);
        this.start();
    },
    events: function() {
        this.loading();
        this.update_status();
        this.it = {
            namespaces: this.rest("GET","/api/namespace").namespaces
        };
        if (this.application.current.query.namespace) {
            this.it.events = this.rest("GET","/api/event?namespace=" + this.application.current.query.namespace).events;
        } else {
            this.it.events = this.rest("GET","/api/event").events;
        }
        this.application.render(this.it);
        this.start();
    },
    config: function() {
        this.update_status();
        this.it = {
            fields: this.rest("OPTIONS","/api/config", {config: this.rest("GET","/api/config").config}).fields
        };
        this.application.render(this.it);
    },
    config_input: function() {
        var config = {};
        for (var field_index = 0; field_index < this.it.fields.length; field_index++) {
            var field = this.it.fields[field_index];
            config[field.name] = {}
            for (var subfield_index = 0; subfield_index < field.fields.length; subfield_index++) {
                var subfield = field.fields[subfield_index];
                if (subfield.options) {
                    config[field.name][subfield.name] = $("input[name='" + field.name + '-' + subfield.name + "']:checked").val()
                } else {
                    config[field.name][subfield.name] = $("#" + field.name + '-' + subfield.name).val()
                }
            }
        }
        return config;
    },
    config_change: function() {
        this.loading();
        this.it = {
            fields: this.rest("OPTIONS","/api/config", {config: this.config_input()}).fields
        };
        this.application.render(this.it);
    },
    config_update: function() {
        this.loading();
        var config =  this.config_input();
        this.it = this.rest("OPTIONS","/api/config", {config: config});
        if (!this.it.errors) {
            this.rest("POST","/api/config", {config: config});
            this.it.message = "config saved";
            if (window.location.hostname.split('.')[1] == "local") {
                if (config["kubernetes"]["role"] == "master" || config["kubernetes"]["role"] == "worker") {
                    this.switch = "http://" + config.kubernetes.cluster + "-klot-io.local";
                } else {
                    this.switch = "http://klot-io.local";
                }
                this.check = "checking " + this.switch + "...";
                this.timeout = window.setTimeout($.proxy(this.config_switch,this), 5000);
            }
        }
        this.application.render(this.it);
    },
    config_switch: function() {
        this.it.message = this.check;
        this.check += ".";
        window.location.hostname.split('.')[1]
        var response = $.ajax({url: this.switch + "/api/health", async: false});
        if (response.status == 200) {
            window.location = this.switch;
            this.check = null;
            this.switch = null;
        } else {
            this.timeout = window.setTimeout($.proxy(this.config_switch,this), 5000);
        }
    },
    status: function() {
        this.loading();
        this.update_status();
        this.application.render({});
        this.start();
    },
    nodes: function() {
        this.loading();
        this.update_status();
        this.it = {
            nodes: this.rest("GET","/api/node").nodes
        }
        this.application.render(this.it);
        this.start();
    },
    node_join: function() {
        this.loading();
        this.rest("POST","/api/node", {node: {name: $("#name").val()}})
        this.application.go('nodes');
    },
    node_reset: function(node) {
        if (confirm("Are you sure you want to reset " + node + "?")) {
            this.loading();
            this.rest("DELETE","/api/node", {node: node});
            this.application.go('nodes');
        }
    },
    pods: function() {
        this.loading();
        this.update_status();
        this.it = {
            namespaces: this.rest("GET","/api/namespace").namespaces,
            pods: this.rest("GET","/api/pod").pods
        }

        this.it = {
            namespaces: this.rest("GET","/api/namespace").namespaces
        };
        if (this.application.current.query.namespace) {
            this.it.pods = this.rest("GET","/api/pod?namespace=" + this.application.current.query.namespace).pods;
        } else {
            this.it.pods = this.rest("GET","/api/pod").pods;
        }
        this.application.render(this.it);
        this.start();
    },
    pod: function() {
        this.loading();
        this.update_status();
        this.it = {
            log: this.rest("GET","/api/pod/" + this.application.current.path.pod).log
        };
        this.application.render(this.it);
        this.start();
    },
    pod_delete: function(pod) {
        if (confirm("Are you sure you want to delete " + pod + "?")) {
            this.rest("DELETE","/api/pod/" + pod);
            this.application.refresh();
        }
    },
    apps: function() {
        this.loading();
        this.update_status();
        this.it = {
            apps: this.rest("GET","/api/app").apps
        }
        this.application.render(this.it);
        this.start();
    },
    apps_change: function() {
        this.stop();
        var from = $("input[name='from']:checked").val();
        if (from == "url") {
            $("#from_url").show();
            $("#from_github").hide();
        } else if (from == "github") {
            $("#from_url").hide();
            $("#from_github").show();
        }
        $("#apps_action").show();
    },
    apps_source: function() {
        var from = $("input[name='from']:checked").val();
        var source = {};
        if (from == "url") {
            source['url'] = $("#url").val();
        } else if (from == "github") {
            source["site"] = "github.com";
            source['repo']= $("#repo").val();
            if ($("#version").val()) {
                source["version"] = $("#version").val()
            }
            if ($("#path").val()) {
                source["path"] = $("#path").val()
            }
        }
        return source;
    },
    apps_action: function(action) {
        var name = $("#name").val();
        this.it.message = this.rest("POST","/api/app", {name: name, source: this.apps_source(), action: action}).message;
        this.application.refresh();
    },
    app_action: function(name, action) {
        if (action == "Settings") {
            this.application.go("settings", name);
        } else if (action == "Upgrade") {
            this.application.go("upgrade", name);
        } else if (action == "Delete") {
            this.rest("DELETE","/api/app/" + name);
            if (this.application.current.path.app_name) {
                this.application.go('apps');
            } else {
                this.application.refresh();
            }
        } else if (action != "Uninstall" || confirm("Are you sure you want to uninstall " + name + "?")) {
            this.rest("PATCH","/api/app/" + name, {action: action});
            this.application.refresh();
        }
    },
    info: function() {
        this.loading();
        this.update_status();
        this.it = {
            app: this.rest("GET","/api/app/"+ DRApp.current.path.app_name).app
        }
        this.application.render(this.it);
        this.start();
    },
    settings: function() {
        var settings = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name, {});
        this.it = {
            app: this.rest("GET","/api/app/"+ DRApp.current.path.app_name).app,
            fields: settings.fields,
            ready: settings.ready
        }
        this.application.render(this.it);
    },
    settings_input: function() {
        var values = {};
        for (var field_index = 0; field_index < this.it.fields.length; field_index++) {
            var field = this.it.fields[field_index];
            if (field.fields) {
                values[field.name] = {}
                for (var subfield_index = 0; subfield_index < field.fields.length; subfield_index++) {
                    var subfield = field.fields[subfield_index];
                    if (subfield.options) {
                        if (field.multi) {
                            values[field.name][subfield.name] = [];
                            $("input[name='" + field.name + '-' + subfield.name + "']:checked").each(function () {
                                values[field.name][subfield.name].push($(this).val());
                            });
                        } else {
                            values[field.name][subfield.name] = $("input[name='" + field.name + '-' + subfield.name + "']:checked").val()
                        }
                    } else {
                        values[field.name][subfield.name] = $("#" + field.name + '-' + subfield.name).val()
                    }
                }
            } else if (field.options) {
                if (field.multi) {
                    values[field.name] = [];
                    $("input[name='" + field.name + "']:checked").each(function () {
                        values[field.name].push($(this).val());
                    });
                } else {
                    values[field.name] = $("input[name='" + field.name + "']:checked").val()
                }
            } else {
                values[field.name] = $("#" + field.name).val()
            }
        }
        return values;
    },
    settings_next: function() {
        var values = this.settings_input();
        var settings = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name, {values: values});
        this.it.fields = settings.fields;
        this.it.ready = settings.ready;
        this.application.render(this.it);
    },
    settings_save: function() {
        var values = this.settings_input();
        var settings = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name, {values: values, validate: true});
        this.it.fields = settings.fields;
        this.it.ready = settings.ready;
        this.it.errors = settings.errors;
        if (!this.it.errors) {
            this.rest("PUT","/api/app/"+ DRApp.current.path.app_name, {values: values});
            this.application.go("apps");
        } else {
            this.application.render(this.it);
        }
    },
    settings_cancel: function() {
        this.application.go("apps");
    },
    upgrade: function() {
        var upgrade = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name + '/upgrade', {});
        this.it = {
            app: this.rest("GET","/api/app/"+ DRApp.current.path.app_name).app,
            fields: upgrade.fields,
            ready: upgrade.ready
        }
        this.application.render(this.it);
    },
    upgrade_input: function() {
        var values = {};
        for (var field_index = 0; field_index < this.it.fields.length; field_index++) {
            var field = this.it.fields[field_index];
            if (field.options) {
                values[field.name] = $("input[name='" + field.name + "']:checked").val();
            }
        }
        return values;
    },
    upgrade_change: function() {
        var values = this.upgrade_input();
        var upgrade = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name + '/upgrade', {values: values});
        this.it.fields = upgrade.fields;
        this.it.ready = upgrade.ready;
        this.it.errors = upgrade.errors;
        this.application.render(this.it);
    },
    upgrade_save: function() {
        var values = this.upgrade_input();
        var upgrade = this.rest("OPTIONS","/api/app/"+ DRApp.current.path.app_name + '/upgrade', {values: values, validate: true});
        this.it.fields = upgrade.fields;
        this.it.ready = upgrade.ready;
        this.it.errors = upgrade.errors;
        if (!this.it.errors) {
            this.rest("PUT","/api/app/"+ DRApp.current.path.app_name + '/upgrade', {values: values});
            this.application.go("apps");
        } else {
            this.application.render(this.it);
        }
    },
    upgrade_cancel: function() {
        this.application.go("apps");
    }
});

DRApp.partial("Header",DRApp.load("header"));
DRApp.partial("Footer",DRApp.load("footer"));

DRApp.template("Home",DRApp.load("home"),null,DRApp.partials);
DRApp.template("Login",DRApp.load("login"),null,DRApp.partials);
DRApp.template("Logs",DRApp.load("logs"),null,DRApp.partials);
DRApp.template("Events",DRApp.load("events"),null,DRApp.partials);
DRApp.template("Config",DRApp.load("config"),null,DRApp.partials);
DRApp.template("Status",DRApp.load("status"),null,DRApp.partials);
DRApp.template("Pods",DRApp.load("pods"),null,DRApp.partials);
DRApp.template("Pod",DRApp.load("pod"),null,DRApp.partials);
DRApp.template("Nodes",DRApp.load("nodes"),null,DRApp.partials);
DRApp.template("Apps",DRApp.load("apps"),null,DRApp.partials);
DRApp.template("Info",DRApp.load("info"),null,DRApp.partials);
DRApp.template("Settings",DRApp.load("settings"),null,DRApp.partials);
DRApp.template("Upgrade",DRApp.load("upgrade"),null,DRApp.partials);

DRApp.route("home","/","Home","Base", "home")
DRApp.route("login","/login","Login","Base", "login")
DRApp.route("logout","/logout","Login","Base", "logout")
DRApp.route("logs","/log/{service}","Logs","Base", "logs", "stop")
DRApp.route("events","/event","Events","Base", "events", "stop")
DRApp.route("config","/config","Config","Base","config", "stop");
DRApp.route("status","/status","Status","Base","status", "stop");
DRApp.route("pods","/pod","Pods","Base","pods", "stop");
DRApp.route("pod","/pod/{pod}","Pod","Base","pod", "stop");
DRApp.route("nodes","/node","Nodes","Base","nodes", "stop");
DRApp.route("apps","/app","Apps","Base","apps", "stop");
DRApp.route("info","/app/{app_name}/info","Info","Base","info", "stop");
DRApp.route("settings","/app/{app_name}/settings","Settings","Base","settings");
DRApp.route("upgrade","/app/{app_name}/upgrade","Upgrade","Base","upgrade");
