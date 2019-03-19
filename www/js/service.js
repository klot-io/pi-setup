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
    "Workers": 7
};

DRApp.status =  "Login";

DRApp.controller("Base",null,{
    timeout: null,
    loading: function() {
        $("#spinner").show();
    },
    start: function() {
        this.stop();
        this.timeout = window.setTimeout($.proxy(this.update,this), 5000);
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
    rest: function(type,url,data,success,error,complete) {
        var response = $.ajax({
            type: type,
            url: url,
            contentType: "application/json",
            headers: {'klot-io-password': DRApp.password},
            data: (data === null) ? null : JSON.stringify(data),
            dataType: "json",
            async: false
        });
        if ((response.status != 200) && (response.status != 201) && (response.status != 202)) {
            alert(type + ": " + url + " failed");
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
            this.application.go("pod");
        } else if (DRApp.status == "Master") {
            this.application.go("node");
        } else if (DRApp.status == "Workers") {
            this.application.go("app");
        } else {
            this.application.render(this.it);
        }
    },
    login: function() {
        this.application.render(this.it);
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
    config: function() {
        this.update_status();
        this.it = {
            settings: this.rest("OPTIONS","/api/config", {config: this.rest("GET","/api/config").config}).settings
        };
        this.application.render(this.it);
    },
    config_input: function() {
        var config = {};
        for (var setting_index = 0; setting_index < this.it.settings.length; setting_index++) {
            var setting = this.it.settings[setting_index];
            config[setting.name] = {}
            for (var field_index = 0; field_index < setting.fields.length; field_index++) {
                var field = setting.fields[field_index];
                if (field.options) {
                    config[setting.name][field.name] = $("input[name='" + setting.name + '-' + field.name + "']:checked").val()
                } else {
                    config[setting.name][field.name] = $("#" + setting.name + '-' + field.name).val()
                }
            }
        }
        return config;
    },
    config_change: function() {
        this.loading();
        this.it = {
            settings: this.rest("OPTIONS","/api/config", {config: this.config_input()}).settings
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
    node: function() {
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
        this.application.go('node');
    },
    node_delete: function(node) {
        this.loading();
        this.rest("DELETE","/api/node", {node: node});
        this.application.go('node');
    },
    pod: function() {
        this.loading();
        this.it = {
            pods: this.rest("GET","/api/pod").pods
        }
        this.application.render(this.it);
        this.start();
    },
    app: function() {
        this.loading();
        this.it = {
            app: []
        }
        this.application.render(this.it);
        this.start();
    }
});

DRApp.partial("Header",DRApp.load("header"));
DRApp.partial("Footer",DRApp.load("footer"));

DRApp.template("Home",DRApp.load("home"),null,DRApp.partials);
DRApp.template("Login",DRApp.load("login"),null,DRApp.partials);
DRApp.template("Config",DRApp.load("config"),null,DRApp.partials);
DRApp.template("Status",DRApp.load("status"),null,DRApp.partials);
DRApp.template("Pod",DRApp.load("pod"),null,DRApp.partials);
DRApp.template("Node",DRApp.load("node"),null,DRApp.partials);
DRApp.template("App",DRApp.load("app"),null,DRApp.partials);

DRApp.route("home","/","Home","Base", "home")
DRApp.route("login","/login","Login","Base", "login")
DRApp.route("logout","/logout","Login","Base", "logout")
DRApp.route("config","/config","Config","Base","config", "stop");
DRApp.route("status","/status","Status","Base","status", "stop");
DRApp.route("pod","/pod","Pod","Base","pod", "stop");
DRApp.route("node","/node","Node","Base","node", "stop");
DRApp.route("app","/app","App","Base","app", "stop");
