HERMES_PLUGIN_DIR ?= $(HOME)/.hermes/plugins/napcat
HERMES_AGENT_DIR ?= ./hermes-agent
SOURCE_DIR ?= ./src/napcat
DEV_LINK ?= $(HERMES_AGENT_DIR)/plugins/platforms/napcat

.PHONY: dev deploy undeploy clean test

# Symlink source into hermes-agent for development/testing
dev:
	@echo "==> Symlinking source into Hermes repo for development"
	@mkdir -p "$(HERMES_AGENT_DIR)/plugins/platforms"
	@rm -rf "$(DEV_LINK)"
	@ln -s "$(realpath $(SOURCE_DIR))" "$(DEV_LINK)"
	@echo "==> Done. Source at $(DEV_LINK) → $(SOURCE_DIR)"

# Deploy to ~/.hermes/plugins/napcat/ for production use
deploy:
	@echo "==> Deploying napcat plugin to $(HERMES_PLUGIN_DIR)"
	@mkdir -p "$(HOME)/.hermes/plugins"
	@rm -rf "$(HERMES_PLUGIN_DIR)"
	@cp -r "$(SOURCE_DIR)" "$(HERMES_PLUGIN_DIR)"
	@echo "==> Done. Enable: hermes plugins enable napcat-platform"

undeploy:
	@echo "==> Removing napcat plugin"
	@rm -rf "$(DEV_LINK)"
	@rm -rf "$(HERMES_PLUGIN_DIR)"
	@echo "==> Done"

test: dev
	@cd "$(HERMES_AGENT_DIR)" && uv run python3 -c '\
import sys; sys.path.insert(0, "."); \
from plugins.platforms.napcat.onebot_event import OneBotEventParser; \
from plugins.platforms.napcat.onebot_client import OneBotClientManager; \
from gateway.config import Platform; \
from gateway.platforms.base import MessageType; \
parser = OneBotEventParser(Platform("napcat")); \
\
e = parser.parse({"post_type":"message","message_type":"private","user_id":200,"message":"Hi","sender":{"nickname":"U"},"message_id":"1","self_id":"100"}, "100"); \
assert e is not None and e.text == "Hi" and e.source.chat_type == "dm"; print("OK   private message"); \
\
e = parser.parse({"post_type":"message","message_type":"group","group_id":300,"user_id":200,"message":"[CQ:reply,id=-1]Hi [CQ:at,qq=999]","sender":{"nickname":"U"},"message_id":"2","self_id":"100"}, "100"); \
assert e is not None and "Hi" in e.text and e.reply_to_message_id == "-1"; print("OK   group msg + CQ"); \
\
e = parser.parse({"post_type":"meta_event","meta_event_type":"heartbeat","self_id":"100","status":{},"time":1}, "100"); \
assert e is None; print("OK   heartbeat skip"); \
\
e = parser.parse({"post_type":"message","message_type":"private","user_id":200,"message":"[CQ:image,file=x,url=http://x.com/x.jpg]","sender":{"nickname":"U"},"message_id":"3","self_id":"100"}, "100"); \
assert e is not None and e.message_type == MessageType.PHOTO; print("OK   image -> PHOTO"); \
\
cm = OneBotClientManager(); assert cm.client_count == 0; print("OK   client manager"); \
\
print("All tests passed.")'

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
