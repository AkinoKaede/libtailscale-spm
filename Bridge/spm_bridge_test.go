//go:build darwin || ios

package main

import (
	"context"
	"testing"
	"time"
)

func TestBridgeCancellationReachesPendingOperation(t *testing.T) {
	id := LtNewOperation()
	defer LtReleaseOperation(id)
	ctx, cancel := operationContext(id, 30)
	defer cancel()
	LtCancelOperation(id)
	select {
	case <-ctx.Done():
		if ctx.Err() != context.Canceled {
			t.Fatal(ctx.Err())
		}
	case <-time.After(time.Second):
		t.Fatal("cancellation did not reach operation")
	}
}

func TestReleasedOperationCannotBeReused(t *testing.T) {
	id := LtNewOperation()
	LtReleaseOperation(id)
	ctx, cancel := operationContext(id, 30)
	defer cancel()
	if ctx.Err() != context.Canceled {
		t.Fatal("released operation was accepted")
	}
	LtCancelOperation(id)
	LtReleaseOperation(id)
}
