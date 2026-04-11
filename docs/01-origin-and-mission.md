# Origin And Mission

## Why This Project Exists

This project began from a concrete human problem, not from a generic startup idea.

A friend has a grandmother with Alzheimer's. That immediately creates a care environment with difficult realities:

- daily routines are easy to miss or misremember
- medicines matter, but adherence is fragile
- household hazards carry disproportionate risk
- caregivers are not physically present every minute
- uncertainty itself becomes exhausting for families

The purpose of the project is to reduce that uncertainty.

## Core Problem Statement

Families caring for someone with Alzheimer's need a system that can do three things at once:

1. observe what is happening in the home
2. interpret the safety significance of what it sees
3. notify the right people quickly and clearly, through every channel available

Most tools solve only one slice:

- pill reminders without visual confirmation
- cameras without care-specific intelligence
- messaging tools without household context

This project is an attempt to unify those pieces.

## Product Goal

The product goal is to build a home-care safety copilot for Alzheimer's patients that can:

- recognize medicine bottles and convert them into reminder schedules
- learn which faces are familiar and flag unfamiliar ones
- detect immediate hazards such as fire, sharp objects, or weapons
- keep caregivers informed without requiring constant manual monitoring
- deliver alerts through multiple channels: SMS, MMS, and email
- extend camera coverage to any phone in the home without requiring an app

## Design Principle

The guiding principle is simple:

**make safety events visible early enough to change the outcome.**

That means the system is optimized around:

- low-friction onboarding
- near-real-time feedback
- persistent event history
- practical caregiver escalation through SMS, MMS, and email
- extensible camera coverage through the phone network

## Who The Product Is For

The primary user is not one person. It is a care pair:

- the patient, who needs reminders and protection
- the caregiver, who needs situational awareness and escalation context

The dashboard therefore acts as a shared operational surface rather than a single-user app. Notifications reach both the patient and caregiver through their preferred channels: phone, email, or both.

## What "Success" Means For This Project

Success is not measured by model novelty.

Success means:

- a medicine in view becomes a structured medication record
- that medication becomes reminders without manual data entry
- those reminders arrive via SMS and email at the right times
- a dangerous event becomes an alert with enough context to act
- that alert reaches the caregiver through every configured channel with image evidence
- a caregiver can understand the patient's state quickly from one dashboard
- any phone in the home can extend the system's field of view

## Why Vision Matters Here

Alzheimer's care has a very specific failure pattern:

- the patient may not reliably report what happened
- the caregiver may only find out after the window to intervene has passed

Computer vision is useful here not because it is trendy, but because it can act as an ambient witness. The multi-camera phone network extends that witness to every room in the house.

## Why The System Combines Vision And Workflow

A camera alone is not enough.

Detection alone is not enough.

The project combines:

- perception (YOLOv8, Roboflow, Gemini, face_recognition)
- interpretation (pipeline logic for medicines, faces, hazards)
- persistence (Supabase for structured data and image evidence)
- scheduling (APScheduler for medicine reminders)
- notification (Twilio for SMS/MMS, SendGrid for email)
- multi-camera coverage (phone network for extended surveillance)

That is the product thesis. The software is not just trying to classify images. It is trying to turn observed events into care actions, and deliver those actions through every channel that reaches the people who need them.

## Ethical And Practical Framing

This system should be understood as assistive monitoring infrastructure, not autonomous medical decision-making.

Its job is to:

- improve visibility
- reduce delay
- support caregivers
- create a usable record of events

Its job is not to replace medical professionals, replace family judgment, or make clinical decisions on its own.

## The Mission In One Sentence

Build a home safety system that helps families care for an Alzheimer's patient with more awareness, faster response, and less guesswork, delivered through every communication channel available and powered by cameras they already own.
