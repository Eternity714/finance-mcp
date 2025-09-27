// SSE客户端 - 处理服务器推送事件
class SSEClient {
    constructor() {
        this.eventSource = null;
        this.isConnected = false;
        this.reconnectInterval = 5000;
        this.maxReconnectAttempts = 10;
        this.reconnectAttempts = 0;
        this.eventHandlers = {};
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        try {
            this.eventSource = new EventSource('/sse/connect');

            this.eventSource.onopen = () => {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus('已连接');
                this.addLogEntry('✅ SSE连接已建立', 'success');
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    this.addLogEntry(`❌ SSE消息解析失败: ${error.message}`, 'error');
                }
            };

            this.eventSource.onerror = (error) => {
                this.isConnected = false;
                this.updateConnectionStatus('连接错误');
                this.addLogEntry('❌ SSE连接发生错误', 'error');

                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    setTimeout(() => {
                        this.reconnectAttempts++;
                        this.addLogEntry(`🔄 尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'info');
                        this.connect();
                    }, this.reconnectInterval);
                }
            };

            // 监听自定义事件类型
            this.eventSource.addEventListener('stock_update', (event) => {
                const data = JSON.parse(event.data);
                this.addLogEntry(`📊 股票更新: ${data.symbol} - ${data.price}`, 'info');
            });

            this.eventSource.addEventListener('news_update', (event) => {
                const data = JSON.parse(event.data);
                this.addLogEntry(`📰 新闻更新: ${data.title}`, 'info');
            });

        } catch (error) {
            this.addLogEntry(`❌ SSE连接失败: ${error.message}`, 'error');
        }
    }

    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
            this.updateConnectionStatus('已断开');
            this.addLogEntry('🔌 SSE连接已断开', 'info');
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'stock_data':
                this.addLogEntry(`📊 股票数据: ${JSON.stringify(data.payload)}`, 'info');
                break;
            case 'news':
                this.addLogEntry(`📰 新闻: ${data.payload.title}`, 'info');
                break;
            case 'system':
                this.addLogEntry(`🔧 系统消息: ${data.message}`, 'info');
                break;
            default:
                this.addLogEntry(`📨 收到消息: ${JSON.stringify(data)}`, 'info');
        }
    }

    updateConnectionStatus(status) {
        const statusElement = document.getElementById('sse-status-value');
        const cardElement = document.getElementById('sse-status');

        if (statusElement) {
            statusElement.textContent = status;
        }

        if (cardElement) {
            cardElement.className = 'status-card ' +
                (this.isConnected ? 'success' : 'error');
        }
    }

    addLogEntry(message, type = 'info') {
        if (typeof window.addLogEntry === 'function') {
            window.addLogEntry(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    on(eventType, handler) {
        this.eventHandlers[eventType] = handler;
    }
}

// 创建全局SSE客户端实例
window.sseClient = new SSEClient();

// 全局连接函数
function connectSSE() {
    window.sseClient.connect();
}

function disconnectSSE() {
    window.sseClient.disconnect();
}