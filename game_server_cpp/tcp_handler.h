#ifndef TCP_HANDLER_H
#define TCP_HANDLER_H

#include <boost/asio.hpp>
#include <vector>
#include <memory> // For std::shared_ptr
#include "tcp_session.h"
#include "stubs.h" // For SessionManagerStub, TankPoolStub
#include <amqp.h>  // For amqp_connection_state_t

using boost::asio::ip::tcp;

class GameTCPServer {
public:
    GameTCPServer(boost::asio::io_context& io_context, short port,
                  SessionManagerStub& sm_stub,
                  TankPoolStub& tp_stub,
                  amqp_connection_state_t rabbitmq_conn_state); // Pass AMQP connection state

private:
    void do_accept();
    void handle_accept(std::shared_ptr<GameTCPSession> new_session,
                       const boost::system::error_code& error);

    tcp::acceptor acceptor_;
    SessionManagerStub& session_manager_stub_;
    TankPoolStub& tank_pool_stub_;
    amqp_connection_state_t rabbitmq_conn_state_; // Store AMQP connection state
};

#endif // TCP_HANDLER_H
