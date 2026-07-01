import { PassageText } from '@cyo/design-system'

export function SingleParagraph() {
  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <PassageText
        text="You stand at the edge of Thornwood Forest. The ancient trees stretch so high their canopy blots out the afternoon sun. Somewhere deep within, a branch snaps, and a flock of starlings bursts skyward in a dark, swirling cloud."
      />
    </div>
  )
}

export function MultiParagraph() {
  return (
    <div style={{ padding: '32px', maxWidth: '600px' }}>
      <PassageText
        text={`The map crinkles in your hands as you unfold it for the third time. Every path leads somewhere, but only one leads to the Dragon's Eye gem, and you have until sundown to find it.

Your best friend Maya tugs at your sleeve. "The old bridge or the rope crossing?" she asks. Neither choice seems particularly safe. The wooden bridge is half-rotten, its planks missing like teeth. The rope crossing sways alarmingly in the breeze.

You look at the river below, dark green and rushing fast. A fish leaps, catches the light, and vanishes. Your heart races. This is really happening.`}
      />
    </div>
  )
}
