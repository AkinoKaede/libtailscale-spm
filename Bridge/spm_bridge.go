//go:build darwin || ios

package main

/*
#cgo darwin LDFLAGS: -framework Security -framework CoreFoundation
#cgo ios LDFLAGS: -framework Security -framework CoreFoundation
#include <stdlib.h>
#include "spm_bridge.h"
*/
import "C"

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"runtime/debug"
	"strings"
	"sync"
	"time"
	"unsafe"

	"tailscale.com/ipn"
)

type secureStore struct{ scope string }

func (s *secureStore) ReadState(key ipn.StateKey) ([]byte, error) {
	scope, name := C.CString(s.scope), C.CString(string(key))
	defer C.free(unsafe.Pointer(scope))
	defer C.free(unsafe.Pointer(name))
	var data unsafe.Pointer
	var length C.int
	code := C.lt_store_read(scope, name, &data, &length)
	if code == -25300 {
		return nil, ipn.ErrStateNotExist
	}
	if code != 0 {
		return nil, fmt.Errorf("state read failed (%d)", code)
	}
	defer C.free(data)
	return C.GoBytes(data, length), nil
}
func (s *secureStore) WriteState(key ipn.StateKey, value []byte) error {
	scope, name := C.CString(s.scope), C.CString(string(key))
	defer C.free(unsafe.Pointer(scope))
	defer C.free(unsafe.Pointer(name))
	data := C.CBytes(value)
	defer C.free(data)
	if code := C.lt_store_write(scope, name, data, C.int(len(value))); code != 0 {
		return fmt.Errorf("state write failed (%d)", code)
	}
	return nil
}

//export LtConfigureStore
func LtConfigureStore(node C.int, scope *C.char) C.int {
	s := getServer(node)
	if s == nil || s.started {
		return -1
	}
	s.s.Store = &secureStore{scope: C.GoString(scope)}
	return 0
}

type operation struct {
	ctx    context.Context
	cancel context.CancelFunc
}

var operations = struct {
	sync.Mutex
	next    uint64
	entries map[uint64]operation
}{entries: make(map[uint64]operation)}

//export LtNewOperation
func LtNewOperation() C.ulonglong {
	operations.Lock()
	defer operations.Unlock()
	operations.next++
	ctx, cancel := context.WithCancel(context.Background())
	operations.entries[operations.next] = operation{ctx, cancel}
	return C.ulonglong(operations.next)
}

//export LtCancelOperation
func LtCancelOperation(id C.ulonglong) {
	operations.Lock()
	defer operations.Unlock()
	if op, ok := operations.entries[uint64(id)]; ok {
		op.cancel()
	}
}

//export LtReleaseOperation
func LtReleaseOperation(id C.ulonglong) {
	operations.Lock()
	defer operations.Unlock()
	if op, ok := operations.entries[uint64(id)]; ok {
		op.cancel()
		delete(operations.entries, uint64(id))
	}
}
func operationContext(id C.ulonglong, seconds C.int) (context.Context, context.CancelFunc) {
	operations.Lock()
	op, ok := operations.entries[uint64(id)]
	operations.Unlock()
	if !ok {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		return ctx, cancel
	}
	return context.WithTimeout(op.ctx, time.Duration(seconds)*time.Second)
}
func bridgeError(err error, out **C.char) C.int {
	if err == nil {
		return 0
	}
	*out = C.CString(err.Error())
	return -1
}

//export LtDial
func LtDial(node C.int, address *C.char, id C.ulonglong, seconds C.int, fd *C.int, errorOut **C.char) C.int {
	*fd = -1
	s := getServer(node)
	if s == nil {
		return bridgeError(fmt.Errorf("node is closed"), errorOut)
	}
	ctx, cancel := operationContext(id, seconds)
	defer cancel()
	conn, err := s.s.Dial(ctx, "tcp", C.GoString(address))
	if err != nil {
		return bridgeError(err, errorOut)
	}
	if err := newConn(s, conn, fd); err != nil {
		conn.Close()
		return bridgeError(err, errorOut)
	}
	return 0
}

//export LtRequest
func LtRequest(node C.int, method, path, body *C.char, id C.ulonglong, seconds C.int, response, errorOut **C.char) C.int {
	s := getServer(node)
	if s == nil {
		return bridgeError(fmt.Errorf("node is closed"), errorOut)
	}
	ctx, cancel := operationContext(id, seconds)
	defer cancel()
	lc, err := s.s.LocalClient()
	if err != nil {
		return bridgeError(err, errorOut)
	}
	req, err := http.NewRequestWithContext(ctx, C.GoString(method), "http://local-tailscaled.sock/localapi/v0/"+C.GoString(path), strings.NewReader(C.GoString(body)))
	if err != nil {
		return bridgeError(err, errorOut)
	}
	req.Header.Set("Content-Type", "application/json")
	res, err := lc.DoLocalRequest(req)
	if err != nil {
		return bridgeError(err, errorOut)
	}
	defer res.Body.Close()
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		return bridgeError(fmt.Errorf("LocalAPI returned HTTP %d", res.StatusCode), errorOut)
	}
	data, err := io.ReadAll(io.LimitReader(res.Body, 32<<20))
	if err != nil {
		return bridgeError(err, errorOut)
	}
	*response = C.CString(string(data))
	return 0
}

//export LtVersion
func LtVersion() *C.char {
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, dependency := range info.Deps {
			if dependency.Path == "tailscale.com" {
				if dependency.Replace != nil {
					dependency = dependency.Replace
				}
				return C.CString(dependency.Version)
			}
		}
	}
	return C.CString("unknown")
}
