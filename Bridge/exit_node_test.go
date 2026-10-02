package main

import (
	"context"
	"io"
	"net"
	"net/http/httptest"
	"net/netip"
	"testing"
	"time"

	"tailscale.com/ipn"
	"tailscale.com/ipn/ipnstate"
	"tailscale.com/net/netns"
	"tailscale.com/tsnet"
	"tailscale.com/tstest/integration"
	"tailscale.com/tstest/integration/testcontrol"
	"tailscale.com/types/logger"
)

// Exercise the same Server.Dial path as LtDial against real userspace nodes.
// Documentation-only destinations are answered exclusively by the selected
// exit node, so a successful dial cannot be a direct Internet connection.
func TestDialUsesSelectedExitNodeWithoutSSH(t *testing.T) {
	netns.SetEnabled(false)
	t.Cleanup(func() { netns.SetEnabled(true) })
	control := &testcontrol.Server{
		DERPMap: integration.RunDERPAndSTUN(t, logger.Discard, "127.0.0.1"),
	}
	control.HTTPTestServer = httptest.NewServer(control)
	t.Cleanup(control.HTTPTestServer.Close)
	ctx, cancel := context.WithTimeout(t.Context(), 45*time.Second)
	defer cancel()
	start := func(name string) (*tsnet.Server, *ipnstate.Status) {
		t.Helper()
		s := &tsnet.Server{
			Dir: t.TempDir(), Hostname: name, ControlURL: control.HTTPTestServer.URL,
			Logf: logger.Discard, UserLogf: logger.Discard,
		}
		t.Cleanup(func() { s.Close() })
		status, err := s.Up(ctx)
		if err != nil {
			t.Fatal(err)
		}
		return s, status
	}
	routes := []netip.Prefix{netip.MustParsePrefix("0.0.0.0/0"), netip.MustParsePrefix("::/0")}
	destinations := []string{"203.0.113.10:443", "[2001:db8::10]:443"}
	var exits []*ipnstate.Status
	for _, name := range []string{"exit-one", "exit-two"} {
		s, status := start(name)
		lc, err := s.LocalClient()
		if err != nil {
			t.Fatal(err)
		}
		if _, err := lc.EditPrefs(ctx, &ipn.MaskedPrefs{
			Prefs: ipn.Prefs{AdvertiseRoutes: routes}, AdvertiseRoutesSet: true,
		}); err != nil {
			t.Fatal(err)
		}
		control.SetSubnetRoutes(status.Self.PublicKey, routes)
		s.RegisterFallbackTCPHandler(func(src, dst netip.AddrPort) (func(net.Conn), bool) {
			if dst.String() != destinations[0] && dst.String() != destinations[1] {
				return nil, false
			}
			return func(c net.Conn) {
				defer c.Close()
				c.SetDeadline(time.Now().Add(5 * time.Second))
				io.WriteString(c, name)
			}, true
		})
		exits = append(exits, status)
	}
	client, _ := start("client")
	lc, err := client.LocalClient()
	if err != nil {
		t.Fatal(err)
	}
	for _, exit := range exits {
		for {
			status, err := lc.Status(ctx)
			if err != nil {
				t.Fatal(err)
			}
			peer := status.Peer[exit.Self.PublicKey]
			if peer != nil && peer.ExitNodeOption {
				if len(peer.SSH_HostKeys) != 0 {
					t.Fatal("exit node must not require SSH")
				}
				break
			}
			select {
			case <-ctx.Done():
				t.Fatal(ctx.Err())
			case <-time.After(20 * time.Millisecond):
			}
		}
		if _, err := lc.EditPrefs(ctx, &ipn.MaskedPrefs{
			Prefs:         ipn.Prefs{ExitNodeID: exit.Self.ID},
			ExitNodeIDSet: true, ExitNodeIPSet: true, AutoExitNodeSet: true,
		}); err != nil {
			t.Fatal(err)
		}
		for _, dst := range destinations {
			conn, err := client.Dial(ctx, "tcp", dst)
			if err != nil {
				t.Fatalf("dial %s via %s: %v", dst, exit.Self.HostName, err)
			}
			conn.SetDeadline(time.Now().Add(5 * time.Second))
			got, err := io.ReadAll(conn)
			conn.Close()
			if err != nil || string(got) != exit.Self.HostName {
				t.Fatalf("dial %s: got %q, %v; want selected exit %s", dst, got, err, exit.Self.HostName)
			}
		}
	}
}
