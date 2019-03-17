window.DRApp = new DoTRoute.Application();

DRApp.load = function (name) {
    return $.ajax({url: name + ".html", async: false}).responseText;
}

DRApp.password = $.cookie('klot-io-password');

DRApp.controller("Base",null,{
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
    home: function() {
        var auth = this.rest("GET","/api/auth");
        if (auth.message == "OK") {
            this.application.render({});
        } else {
            this.application.render({}, "Login");f
        }
    },
    login: function() {
        DRApp.password = $("#password").val();
        $.cookie('klot-io-password', DRApp.password );
        this.application.go("home");
    },
    config: function() {
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
        this.it = {
            settings: this.rest("OPTIONS","/api/config", {config: this.config_input()}).settings
        };
        this.application.render(this.it);
    },
    config_update: function() {
        var config =  this.config_input();
        this.it = this.rest("OPTIONS","/api/config", {config: config});
        if (!this.it.errors) {
            this.rest("POST","/api/config", {config: config});
            this.it.message = "config saved"
        }
        this.application.render(this.it);
    }
});

DRApp.partial("Header",DRApp.load("header"));
DRApp.partial("Footer",DRApp.load("footer"));

DRApp.template("Home",DRApp.load("home"),null,DRApp.partials);
DRApp.template("Login",DRApp.load("login"),null,DRApp.partials);
DRApp.template("Config",DRApp.load("config"),null,DRApp.partials);

DRApp.route("home","/","Home","Base", "home")
DRApp.route("config","/config","Config","Base","config");
